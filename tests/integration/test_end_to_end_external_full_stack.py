"""
F8.6 — External Full-Cycle Closure.

Ferme la seule nuance laissee par F8.5 : le chemin EXTERNE (F8) n'avait
jamais ete exerce dans le MEME cycle que la simulation F4 (scenario 1 de
F8.5 n'utilisait que le roster natif). Aucune nouvelle architecture, aucun
nouveau composant : ce module reutilise strictement KX108GovernanceBridge
(F5), CycleEngine/ExecutionPlanner (F3/F6), CycleReceipt/ReceiptStore/
ReplayEngine (F7), ExternalStackAnalysisAdapter/ExampleBrotherStackAdapter
(F8) — exactement les memes classes que tests/integration/test_end_to_end_full_stack.py.

Chemin prouve en un seul cycle reel :
    External Stack Fixture -> ExternalSignal -> ExternalStackAnalysisAdapter
    -> SourceProvenance (external) -> Canonical Contract (to_canonical_agent_signal,
    meme point de convergence que le natif) -> Simulation F4 (evidence)
    -> TradeIntent -> meme Governance Bridge -> Fixture KX108 -> Canonical
    Decision -> Planner/Binder -> Alpaca PAPER fake -> ExecutionResult
    -> CycleReceipt -> ReceiptStore -> hash-chain -> Audit Replay
    -> Replay deterministe.
"""
from __future__ import annotations

import warnings
from dataclasses import asdict

from domain.market import Bar, MarketSnapshot
from domain.portfolio import AccountState, PortfolioState
from domain.proposal import Consensus, SizingDecision, StrategyCandidate
from domain.provenance import SourceSystem
from domain.receipt import GENESIS_HASH
from domain.types import ActionKind, AssetClass, Authority, DataQuality, Mode, OrderType, Provenance
from execution.binder.engine import CycleEngine
from execution.binder.planner import ExecutionPlanner
from external.adapters.base_adapter import ExternalStackAnalysisAdapter
from external.examples.brother_stack.example_adapter import ExampleBrotherStackAdapter
from governance.bridge.governance_bridge import KX108GovernanceBridge
from proof.receipts.receipt_chain import (
    SIMULATION_EXTENSION_KEY,
    SIMULATION_KIND_TRADING_WORLD,
    build_simulation_extension,
)
from proof.receipts.receipt_store import ReceiptStore
from proof.receipts.receipt_verify import IntegrityStatus, ReceiptChainVerifier
from proof.receipts.replay import DeterministicReplayVerdict, ReplayEngine
from simulation.trading_world.market_process import TradingParams, run_trading_simulation
from tests.test_support.kx108_fixtures import FixtureKX108Client

SYMBOL = "AAPL"

TRADING_PARAMS = TradingParams(
    seed=42, steps=20, s0=100.0, mu=0.05, sigma=0.2, dt=1 / 252,
    jump_lambda=0.01, jump_mu=-0.02, jump_sigma=0.03,
    garch_alpha=0.1, garch_beta=0.85, garch_omega=0.0001,
    regimes=2, friction_bps=5.0,
)


# ── Doubles deterministes (identiques a F8.5, pas de reseau) ────────────────


def _bars(n: int = 30, base: float = 100.0) -> tuple:
    out = []
    price = base
    for i in range(n):
        price = price * (1.0 + (0.001 if i % 2 == 0 else -0.0007))
        out.append(Bar(timestamp=float(i), open=price, high=price * 1.001, low=price * 0.999, close=price, volume=1_000.0))
    return tuple(out)


class FakeMarketData:
    def __init__(self, *, tradable: bool = True, market_open: bool = True, last_price: float = 100.0):
        self._tradable = tradable
        self._market_open = market_open
        self._last_price = last_price
        self._bars = _bars(base=last_price)

    def snapshot(self, symbol: str) -> MarketSnapshot:
        return self.snapshots([symbol])[symbol]

    def snapshots(self, symbols):
        return {
            s: MarketSnapshot(
                symbol=s,
                asset_class=AssetClass.EQUITY,
                last_price=self._last_price,
                provenance=Provenance(source="fake", fetched_at=0.0, quality=DataQuality.LIVE, mode=Mode.PAPER),
                tradable=self._tradable,
                market_open=self._market_open,
                bars=self._bars,
            )
            for s in symbols
        }

    def history(self, symbol, limit=200):
        return ()

    def context(self):
        return None


class FakeBroker:
    """Spy BrokerPort : jamais de reseau."""

    def __init__(self, *, trading_blocked: bool = False):
        self._trading_blocked = trading_blocked
        self.submit_calls = []

    def account(self) -> AccountState:
        return AccountState(
            equity=100_000.0, cash=100_000.0, buying_power=100_000.0,
            provenance=Provenance(source="fake", fetched_at=0.0, quality=DataQuality.LIVE, mode=Mode.PAPER),
            trading_blocked=self._trading_blocked,
        )

    def positions(self):
        return ()

    def open_orders(self):
        return ()

    def portfolio(self) -> PortfolioState:
        return PortfolioState(account=self.account())

    def order_status(self, broker_order_id):
        return None

    def order_by_client_order_id(self, client_order_id):
        return None

    def submit(self, plan):
        self.submit_calls.append(plan)
        from domain.orders import ExecutionResult
        from domain.types import OrderStatus

        return ExecutionResult(
            plan=plan, submitted=True, status=OrderStatus.ACCEPTED,
            broker_order_id="fake-order-external-1", mode=Mode.PAPER.value,
        )

    def cancel(self, plan, broker_order_id):
        raise NotImplementedError

    def replace(self, plan, broker_order_id):
        raise NotImplementedError

    def close_position(self, plan):
        raise NotImplementedError


class FakeAggregation:
    def aggregate(self, outputs):
        return Consensus(side="BUY", confidence=0.62)


class FakeStrategy:
    def build(self, symbol, snapshot, consensus, portfolio, opportunities=()):
        return (
            StrategyCandidate(
                symbol=symbol, action=ActionKind.BUY, rationale="F8.6 external end-to-end",
                confidence=0.62, order_type=OrderType.MARKET, strategy_id="f86-strategy",
            ),
        )


class FakeSizing:
    def size(self, candidate, snapshot, portfolio):
        return SizingDecision(quantity=1.0, requested_quantity=1.0)


def _fixture_client(verdict: str) -> FixtureKX108Client:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # avertissement TEST-ONLY attendu
        return FixtureKX108Client(verdict=verdict)


def _make_external_engine(*, verdict: str, broker: FakeBroker, store, tradable: bool = True) -> CycleEngine:
    bridge = KX108GovernanceBridge(_fixture_client(verdict))
    return CycleEngine(
        market_data=FakeMarketData(tradable=tradable),
        broker=broker,
        analysis=ExternalStackAnalysisAdapter(ExampleBrotherStackAdapter()),  # F8, aucun double
        aggregation=FakeAggregation(),
        authority=bridge,
        symbols=[SYMBOL],
        mode=Mode.PAPER,
        strategy=FakeStrategy(),
        sizing=FakeSizing(),
        planner=ExecutionPlanner(),
        proof=store,
    )


def _attach_simulation_evidence(receipt, params: TradingParams):
    """Meme mecanisme que F8.5 : simulation F4 reellement executee, attachee
    comme EVIDENCE (extensions, jamais Authority) avant persistance."""
    steps, returns = run_trading_simulation(params)
    extension = build_simulation_extension(
        kind=SIMULATION_KIND_TRADING_WORLD, seed=params.seed, params=asdict(params),
        engine_version="market_process.v1", steps=steps, returns=returns,
    )
    receipt.extensions[SIMULATION_EXTENSION_KEY] = extension
    return receipt


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 1 — EXTERNAL + ACT : simulation branchee, ordre PAPER, replay
# ═══════════════════════════════════════════════════════════════════════════


def test_scenario_1_external_act_with_simulation_produces_paper_order_and_replayable_receipt(tmp_path):
    store = ReceiptStore(tmp_path / "receipts.jsonl")
    assert store.last_hash() == GENESIS_HASH

    broker = FakeBroker()
    engine = _make_external_engine(verdict="ACT", broker=broker, store=None)
    # proof=None sur ce premier appel : on persiste manuellement APRES avoir
    # attache la simulation (meme sequence que F8.5 scenario 1).
    outcome = engine.run_cycle()

    assert outcome.decision.authority is Authority.ACT
    assert outcome.plan is not None
    assert outcome.execution is not None and outcome.execution.submitted is True
    assert outcome.touched_the_market is True
    assert len(broker.submit_calls) == 1  # exactement un ordre

    # source_system=external, source_id et adapter_id conserves, produits par
    # le MEME point de convergence (to_canonical_agent_signal) que le natif.
    external_outputs = [
        o for o in outcome.agent_outputs
        if o.source_provenance is not None and o.source_provenance.source_system is SourceSystem.EXTERNAL
    ]
    assert len(external_outputs) == 1
    prov = external_outputs[0].source_provenance
    assert prov.source_id == "brother_strategy_07"
    assert prov.adapter_id == "brother_stack_v1"
    assert prov.organization_id == "brother_company"

    # Simulation F4 reellement executee et attachee comme Evidence AVANT persistance.
    receipt = _attach_simulation_evidence(outcome.receipt, TRADING_PARAMS)
    assert receipt.previous_receipt_hash == GENESIS_HASH
    stored = store.record(receipt)
    assert stored is receipt

    # Provenance externe presente et intacte APRES RELOAD depuis le store (pas juste en memoire).
    reloaded = store.find_by_cycle_id(receipt.cycle_id)
    assert reloaded is not None
    reloaded_outputs = reloaded.raw["decision"]["proposal"]["agent_outputs"]
    reloaded_provenances = [ao["source_provenance"] for ao in reloaded_outputs]
    assert all(p["source_system"] == "external" for p in reloaded_provenances)
    assert all(p["source_id"] == "brother_strategy_07" for p in reloaded_provenances)
    assert all(p["adapter_id"] == "brother_stack_v1" for p in reloaded_provenances)
    # unknowns/risk_flags fournis par la stack externe survivent au reload.
    assert any("stack_externe_non_auditee" in ao.get("unknowns", []) for ao in reloaded_outputs)
    assert any("aucune_verification_independante" in ao.get("risk_flags", []) for ao in reloaded_outputs)
    # La simulation attachee comme evidence est bien celle persistee et rechargee.
    assert SIMULATION_EXTENSION_KEY in reloaded.raw.get("extensions", {})

    # Hash-chain valide pour ce receipt.
    report = ReceiptChainVerifier().verify_store(store)
    assert report.status is IntegrityStatus.VALID

    # Replay audit : reconstruit sans effet de bord (zero appel broker supplementaire).
    replay = ReplayEngine(store)
    audit = replay.replay_audit(receipt.cycle_id)
    assert audit.found is True
    assert audit.kx108_verdict["authority"] == "ACT"
    assert audit.execution["submitted"] is True
    assert len(broker.submit_calls) == 1  # toujours 1 : le replay n'a rien rejoue au broker

    # Replay deterministe : meme seed -> MATCH.
    det_match = replay.replay_deterministic(receipt.cycle_id)
    assert det_match.verdict is DeterministicReplayVerdict.MATCH
    assert len(broker.submit_calls) == 1  # zero appel broker pendant le replay


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 2 — EXTERNAL + BLOCK : aucune execution, evidence/provenance traçables
# ═══════════════════════════════════════════════════════════════════════════


def test_scenario_2_external_block_no_execution_but_evidence_and_provenance_traceable(tmp_path):
    store = ReceiptStore(tmp_path / "receipts.jsonl")
    broker = FakeBroker()
    engine = _make_external_engine(verdict="BLOCK", broker=broker, store=None)
    outcome = engine.run_cycle()

    assert outcome.decision.authority is Authority.BLOCK
    assert outcome.execution is None
    assert broker.submit_calls == []  # aucun broker call

    # Simulation/evidence toujours tracables meme si KX108 bloque : le fait
    # de bloquer ne doit pas empecher de persister ce qui a ete observe/simule.
    receipt = _attach_simulation_evidence(outcome.receipt, TRADING_PARAMS)
    stored = store.record(receipt)
    assert SIMULATION_EXTENSION_KEY in stored.extensions

    # Provenance externe conservee.
    external_outputs = [
        o for o in outcome.agent_outputs
        if o.source_provenance is not None and o.source_provenance.source_system is SourceSystem.EXTERNAL
    ]
    assert len(external_outputs) == 1
    assert external_outputs[0].source_provenance.source_id == "brother_strategy_07"

    # Receipt BLOCK persiste, raison tracable.
    reloaded = store.find_by_cycle_id(receipt.cycle_id)
    assert reloaded is not None
    assert reloaded.authority == "BLOCK"
    assert reloaded.raw["decision"]["metrics"]["kx108_response"]["verdict"] == "BLOCK"

    # Replay fonctionnel sur ce receipt BLOCK aussi.
    audit = ReplayEngine(store).replay_audit(receipt.cycle_id)
    assert audit.found is True
    assert audit.kx108_verdict["authority"] == "BLOCK"
    assert audit.execution is None
    assert broker.submit_calls == []  # toujours aucun appel, meme apres replay


# ═══════════════════════════════════════════════════════════════════════════
# Verifications structurelles — reaffirmees dans CE contexte externe+simulation
# ═══════════════════════════════════════════════════════════════════════════


def test_external_plus_simulation_context_preserves_all_boundaries(tmp_path):
    """
    Assertions groupees prouvant, DANS LE CONTEXTE COMBINE externe+simulation
    (pas seulement isolement), qu'aucune categorie ne s'octroie une autorite
    qui ne lui revient pas :

        External Adapter != Authority / Governance / Binder / Execution
        Simulation != Authority
        Intent != Action
        Decision != Permission
        Receipt != Decision
        Replay != Execution
        Source Provenance != Trust
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2]

    # External Adapter != Binder / Execution / Governance : aucun import REEL
    # (ligne `import ...`/`from ...`, pas une mention en docstring/commentaire)
    # vers execution.binder, market.adapters.alpaca ou governance.bridge dans
    # tout le package external/.
    forbidden_prefixes = ("execution.binder", "market.adapters.alpaca", "market.adapters", "governance.bridge")
    for py_file in (root / "external").rglob("*.py"):
        source = py_file.read_text(encoding="utf-8")
        for ln in source.splitlines():
            stripped = ln.strip()
            if not (stripped.startswith("import ") or stripped.startswith("from ")):
                continue
            for forbidden in forbidden_prefixes:
                assert forbidden not in stripped, (py_file, stripped)

    # Decision != Permission, Intent != Action : KX108=ACT + Binder degrade -> aucun ordre,
    # meme avec la cognition externe (deja prouve isolement F8.5 scenario 4 cote natif ;
    # reconfirme ici cote externe).
    broker_degraded = FakeBroker(trading_blocked=True)
    engine_degraded = _make_external_engine(verdict="ACT", broker=broker_degraded, store=None, tradable=True)
    outcome_degraded = engine_degraded.run_cycle()
    assert outcome_degraded.decision.authority is Authority.ACT  # KX108 Decision...
    assert outcome_degraded.plan is None  # ...!= Binder Permission
    assert broker_degraded.submit_calls == []  # External Adapter != Authority : n'a rien force

    # Simulation != Authority : attacher une simulation ne peut jamais changer
    # une Decision deja figee (le receipt est immuable ; on mute seulement extensions).
    receipt_before = outcome_degraded.receipt
    authority_before = receipt_before.decision.authority
    receipt_after = _attach_simulation_evidence(receipt_before, TRADING_PARAMS)
    assert receipt_after.decision.authority == authority_before  # inchangee

    # Source Provenance != Trust : meme verdict KX108=ACT, cognition externe
    # ou native, produit le meme type de Decision (deja prouve F8.5 scenario 7 ;
    # reconfirme ici avec simulation attachee dans le meme contexte).
    broker_ext = FakeBroker()
    engine_ext_act = _make_external_engine(verdict="ACT", broker=broker_ext, store=None)
    outcome_ext_act = engine_ext_act.run_cycle()
    assert outcome_ext_act.decision.authority is Authority.ACT
    assert outcome_ext_act.touched_the_market is True  # ni penalise ni favorise par source_system=external

    # Receipt != Decision, Replay != Execution : persister/rejouer un receipt
    # externe ne change jamais la Decision ni ne rappelle le broker.
    store = ReceiptStore(tmp_path / "boundaries.jsonl")
    authority_before_persist = outcome_ext_act.decision.authority
    stored = store.record(outcome_ext_act.receipt)
    assert stored.decision.authority == authority_before_persist  # Receipt != Decision

    calls_before_replay = len(broker_ext.submit_calls)
    audit = ReplayEngine(store).replay_audit(outcome_ext_act.cycle_id)
    assert audit.found is True
    assert len(broker_ext.submit_calls) == calls_before_replay  # Replay != Execution
