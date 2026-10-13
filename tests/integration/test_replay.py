"""
F7 — replay audit / replay deterministe, et lien ledger <-> receipts.

Reutilise le cablage complet de test_paper_execution_pipeline.py (F6) plutot
que de le redupliquer : engine reel, FixtureKX108Client (TEST-ONLY),
JsonlOrderLedger (F6), ReceiptStore (F7).
"""
from __future__ import annotations

import warnings

import pytest

from domain.market import MarketSnapshot
from domain.orders import ExecutionResult
from domain.portfolio import AccountState, PortfolioState
from domain.proposal import AgentOutput, Consensus, SizingDecision, StrategyCandidate
from domain.types import ActionKind, AssetClass, DataQuality, Mode, OrderStatus, OrderType, Provenance
from execution.binder.engine import CycleEngine
from execution.binder.order_ledger_jsonl import JsonlOrderLedger
from execution.binder.planner import ExecutionPlanner
from governance.bridge.governance_bridge import KX108GovernanceBridge
from proof.receipts.receipt_store import ReceiptStore
from proof.receipts.replay import DeterministicReplayVerdict, ReplayEngine
from simulation.trading_world.market_process import TradingParams, run_trading_simulation
from proof.receipts.receipt_chain import (
    SIMULATION_KIND_TRADING_WORLD,
    build_simulation_extension,
)
from tests.test_support.kx108_fixtures import FixtureKX108Client

SYMBOL = "AAPL"


class FakeMarketData:
    def snapshot(self, symbol):
        return self.snapshots([symbol])[symbol]

    def snapshots(self, symbols):
        return {
            s: MarketSnapshot(
                symbol=s, asset_class=AssetClass.EQUITY, last_price=100.0,
                provenance=Provenance(source="fake", fetched_at=0.0, quality=DataQuality.LIVE, mode=Mode.PAPER),
                tradable=True, market_open=True,
            )
            for s in symbols
        }

    def history(self, symbol, limit=200):
        return ()

    def context(self):
        return None


class FakeBroker:
    def __init__(self, *, submit_behavior=None):
        self._submit_behavior = submit_behavior or (lambda plan: self._accepted(plan))
        self.submit_calls = []

    @staticmethod
    def _accepted(plan):
        return ExecutionResult(plan=plan, submitted=True, status=OrderStatus.ACCEPTED,
                                broker_order_id="fake-order-1", mode=Mode.PAPER.value)

    def account(self):
        return AccountState(equity=100_000.0, cash=100_000.0, buying_power=100_000.0,
                             provenance=Provenance(source="fake", fetched_at=0.0,
                                                    quality=DataQuality.LIVE, mode=Mode.PAPER),
                             trading_blocked=False)

    def positions(self):
        return ()

    def open_orders(self):
        return ()

    def portfolio(self):
        return PortfolioState(account=self.account())

    def order_status(self, broker_order_id):
        return None

    def order_by_client_order_id(self, client_order_id):
        return None

    def submit(self, plan):
        self.submit_calls.append(plan)
        return self._submit_behavior(plan)

    def cancel(self, plan, broker_order_id):
        raise NotImplementedError

    def replace(self, plan, broker_order_id):
        raise NotImplementedError

    def close_position(self, plan):
        raise NotImplementedError


class FakeAnalysis:
    def analyse(self, symbol, snapshot, portfolio):
        return (
            AgentOutput(
                name="fake-agent", category="test", signal="BUY", confidence=0.9,
                rationale="fixture F7 replay",
                unknowns=("depth_unknown",),
                contradictions=("trend_vs_macro",),
                risk_flags=("liquidity_thin",),
                evidence_refs=("bar:AAPL:2026-09-21T00:00Z",),
            ),
        )


class FakeAggregation:
    def aggregate(self, outputs):
        return Consensus(side="BUY", confidence=0.9)


class FakeStrategy:
    def build(self, symbol, snapshot, consensus, portfolio, opportunities=()):
        return (
            StrategyCandidate(symbol=symbol, action=ActionKind.BUY, rationale="fixture F7",
                               confidence=0.9, order_type=OrderType.MARKET, strategy_id="fixture-strategy"),
        )


class FakeSizing:
    def size(self, candidate, snapshot, portfolio):
        return SizingDecision(quantity=1.0, requested_quantity=1.0)


def _make_engine(*, verdict: str, broker: FakeBroker, proof=None, order_ledger=None):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        kx108 = FixtureKX108Client(verdict=verdict)
    bridge = KX108GovernanceBridge(kx108)
    return CycleEngine(
        market_data=FakeMarketData(),
        broker=broker,
        analysis=FakeAnalysis(),
        aggregation=FakeAggregation(),
        authority=bridge,
        symbols=[SYMBOL],
        mode=Mode.PAPER,
        strategy=FakeStrategy(),
        sizing=FakeSizing(),
        planner=ExecutionPlanner(),
        proof=proof,
        order_ledger=order_ledger,
    )


# ── 10. Replay audit : reconstruit correctement le cycle ───────────────────


def test_audit_replay_reconstructs_the_cycle(tmp_path):
    store = ReceiptStore(tmp_path / "receipts.jsonl")
    outcome = _make_engine(verdict="ACT", broker=FakeBroker(), proof=store).run_cycle()

    result = ReplayEngine(store).replay_audit(outcome.receipt.cycle_id)

    assert result.found is True
    assert result.kx108_verdict["authority"] == "ACT"
    assert result.proposed["symbol"] == SYMBOL
    assert result.binder_decision["touched_the_market"] is True
    assert result.execution["submitted"] is True


def test_audit_replay_unknown_cycle_id_is_not_found(tmp_path):
    store = ReceiptStore(tmp_path / "receipts.jsonl")
    result = ReplayEngine(store).replay_audit("cycle-does-not-exist")
    assert result.found is False


# ── 11-12. Replay deterministe : MATCH / DIVERGENCE ─────────────────────────


def _simulation_receipt_extension(seed: int) -> dict:
    params = TradingParams(
        seed=seed, steps=20, s0=100.0, mu=0.05, sigma=0.2, dt=1 / 252,
        jump_lambda=0.01, jump_mu=-0.02, jump_sigma=0.05,
        garch_alpha=0.1, garch_beta=0.85, garch_omega=0.0001,
        regimes=2, friction_bps=5.0,
    )
    steps, returns = run_trading_simulation(params)
    return build_simulation_extension(
        kind=SIMULATION_KIND_TRADING_WORLD, seed=seed,
        params=params.__dict__, engine_version="market_process.v1",
        steps=steps, returns=returns,
    )


def test_deterministic_replay_same_seed_matches(tmp_path):
    store = ReceiptStore(tmp_path / "receipts.jsonl")

    class AnalysisWithSimulation(FakeAnalysis):
        pass

    outcome = _make_engine(verdict="HOLD", broker=FakeBroker(), proof=None).run_cycle()
    # Attache une extension simulation directement (le pipeline F6 ne branche
    # pas encore simulation/ dans le cycle -- voir dette F7 documentee).
    extension = _simulation_receipt_extension(seed=42)
    enriched = _with_extension(outcome.receipt, extension)
    store.record(enriched)

    result = ReplayEngine(store).replay_deterministic(enriched.cycle_id)
    assert result.verdict == DeterministicReplayVerdict.MATCH
    assert result.original_digest == result.replayed_digest


def test_deterministic_replay_different_seed_diverges(tmp_path):
    """
    Divergence obtenue par une VRAIE re-simulation avec un seed different :
    le receipt stocke le digest calcule avec seed=42, mais ses `params`
    (utilises par le replay pour reconstruire `TradingParams`) portent
    seed=999. Le replay reconstruit donc une trajectoire reellement
    differente et son digest diverge naturellement, sans fabriquer de
    valeur arbitraire.
    """
    store = ReceiptStore(tmp_path / "receipts.jsonl")
    outcome = _make_engine(verdict="HOLD", broker=FakeBroker(), proof=None).run_cycle()

    original_extension = _simulation_receipt_extension(seed=42)
    tampered_params = dict(original_extension["params"])
    tampered_params["seed"] = 999
    tampered_extension = dict(original_extension)
    tampered_extension["params"] = tampered_params
    enriched = _with_extension(outcome.receipt, tampered_extension)
    store.record(enriched)

    result = ReplayEngine(store).replay_deterministic(enriched.cycle_id)
    assert result.verdict == DeterministicReplayVerdict.DIVERGENCE
    assert result.original_digest != result.replayed_digest


def test_deterministic_replay_without_simulation_extension_is_not_replayable(tmp_path):
    store = ReceiptStore(tmp_path / "receipts.jsonl")
    outcome = _make_engine(verdict="HOLD", broker=FakeBroker(), proof=store).run_cycle()

    result = ReplayEngine(store).replay_deterministic(outcome.receipt.cycle_id)
    assert result.verdict == DeterministicReplayVerdict.NOT_REPLAYABLE


def _with_extension(receipt, extension: dict):
    """Retourne un nouveau CycleReceipt portant `extension` sous f7_simulation.

    CycleReceipt est un frozen dataclass (immuabilite deliberee, F3) : on ne
    le mute pas, on en derive un nouveau, comme le fait deja
    `TradingDomainState.with_opportunities` ailleurs dans le domaine.
    """
    import dataclasses

    new_extensions = dict(receipt.extensions)
    new_extensions["f7_simulation"] = extension
    return dataclasses.replace(receipt, extensions=new_extensions)


# ── 13. Replay -> zero appel Alpaca ─────────────────────────────────────────


def test_replay_never_calls_broker(tmp_path):
    store = ReceiptStore(tmp_path / "receipts.jsonl")
    broker = FakeBroker()
    outcome = _make_engine(verdict="ACT", broker=broker, proof=store).run_cycle()
    assert len(broker.submit_calls) == 1  # le cycle original a bien soumis

    ReplayEngine(store).replay_audit(outcome.receipt.cycle_id)
    extension = _simulation_receipt_extension(seed=7)
    enriched = _with_extension(outcome.receipt, extension)
    ReplayEngine(store).replay_deterministic(enriched.cycle_id)  # NOT_REPLAYABLE mais ne doit rien soumettre

    assert len(broker.submit_calls) == 1  # inchange : aucun appel supplementaire pendant le replay


# ── 14. Receipt d'echec broker persiste correctement ────────────────────────


def test_broker_failure_receipt_is_persisted_correctly(tmp_path):
    store = ReceiptStore(tmp_path / "receipts.jsonl")

    def failing_submit(plan):
        raise RuntimeError("Alpaca 500: internal error")

    broker = FakeBroker(submit_behavior=failing_submit)
    outcome = _make_engine(verdict="ACT", broker=broker, proof=store).run_cycle()

    stored = store.find_by_cycle_id(outcome.receipt.cycle_id)
    # Issue ambigue persistee telle quelle : ni succes, ni "non soumis" invente.
    assert stored.raw["execution_result"]["status"] == "UNKNOWN"
    assert "echec de soumission" in stored.raw["execution_result"]["rejected_reason"]
    assert stored.raw["consequence"]["executed"] is False
    assert stored.raw["consequence"]["ambiguous"] is True


# ── 15. BLOCK/HOLD persiste meme sans execution ─────────────────────────────


@pytest.mark.parametrize("verdict", ["BLOCK", "HOLD"])
def test_block_or_hold_receipt_is_persisted_without_execution(tmp_path, verdict):
    store = ReceiptStore(tmp_path / "receipts.jsonl")
    outcome = _make_engine(verdict=verdict, broker=FakeBroker(), proof=store).run_cycle()

    stored = store.find_by_cycle_id(outcome.receipt.cycle_id)
    assert stored is not None
    assert stored.raw["decision"]["authority"] == verdict
    assert stored.raw["execution_plan"] is None
    assert stored.raw["touched_the_market"] is False


# ── 16. Provenance KX108 presente apres persistance + reload ────────────────


def test_kx108_provenance_survives_persistence_and_reload(tmp_path):
    path = tmp_path / "receipts.jsonl"
    store_1 = ReceiptStore(path)
    outcome = _make_engine(verdict="ACT", broker=FakeBroker(), proof=store_1).run_cycle()

    store_2 = ReceiptStore(path)  # reload depuis une nouvelle instance
    stored = store_2.find_by_cycle_id(outcome.receipt.cycle_id)
    kx108_response = stored.raw["decision"]["metrics"]["kx108_response"]
    assert kx108_response["source"] == "FixtureKX108Client (TEST-ONLY)"
    assert kx108_response["verdict"] == "ACT"


# ── 17. unknowns/contradictions/risk_flags survivent persistance + reload ──


def test_agent_evidence_survives_persistence_and_reload(tmp_path):
    path = tmp_path / "receipts.jsonl"
    store_1 = ReceiptStore(path)
    outcome = _make_engine(verdict="HOLD", broker=FakeBroker(), proof=store_1).run_cycle()

    store_2 = ReceiptStore(path)
    stored = store_2.find_by_cycle_id(outcome.receipt.cycle_id)
    agent_outputs = stored.raw["decision"]["proposal"]["agent_outputs"]
    assert agent_outputs[0]["unknowns"] == ["depth_unknown"]
    assert agent_outputs[0]["contradictions"] == ["trend_vs_macro"]
    assert agent_outputs[0]["risk_flags"] == ["liquidity_thin"]
    assert agent_outputs[0]["evidence_refs"] == ["bar:AAPL:2026-09-21T00:00Z"]

    # Meme chemin par le replay audit, pour prouver l'usage reel, pas seulement le stockage brut.
    audit = ReplayEngine(store_2).replay_audit(outcome.receipt.cycle_id)
    assert "depth_unknown" in audit.proposed["unknowns"]
    assert "trend_vs_macro" in audit.proposed["contradictions"]
    assert "liquidity_thin" in audit.proposed["risk_flags"]


# ── 18. verify_integrity() du ledger F6, enfin exercee ──────────────────────


def test_order_ledger_verify_integrity_is_exercised(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    ledger = JsonlOrderLedger(ledger_path)
    _make_engine(verdict="ACT", broker=FakeBroker(), order_ledger=ledger).run_cycle()

    ok, reason = ledger.verify_integrity()
    assert ok is True
    assert reason is None

    # Corrompt le ledger : duplique une ligne pour forcer un event_id en double.
    lines = ledger_path.read_text(encoding="utf-8").splitlines()
    ledger_path.write_text("\n".join(lines + [lines[0]]) + "\n", encoding="utf-8")

    ok, reason = ledger.verify_integrity()
    assert ok is False
    assert "duplicate" in reason
