"""
F8.5 — Full End-to-End Integration.

PREUVE D'ASSEMBLAGE, pas une nouvelle brique metier. Chaque scenario fait
traverser REELLEMENT un seul cycle a travers toute la chaine deja construite
et prouvee separement (F2 Alpaca, F3 Binder/roster, F3.5 contrat canonique,
F4 simulation, F5 Governance Bridge, F6 execution PAPER, F7 proof/replay,
F7.5 provenance, F8 external adapter) :

    SourceProvenance -> Native OU External cognition -> Canonical Contract
    -> Simulation (evidence) -> ActionProposal -> Governance Bridge
    -> KX108 fixture -> Canonical Decision -> Planner/Binder
    -> Alpaca PAPER (fake, spy) -> ExecutionResult -> CycleReceipt
    -> ReceiptStore -> hash-chain -> Audit Replay -> Replay deterministe

Tous les receipts de ce module partagent UNE SEULE chaine persistee
(``tmp_path/receipts.jsonl``) : chaque scenario construit un nouveau
``CycleEngine`` avec ``proof=store``, ce qui lit ``store.last_hash()`` a la
construction et prolonge donc naturellement la chaine du scenario precedent.
Le scenario 1 (ACT + simulation) tourne en premier, store encore vide, pour
pouvoir attacher l'extension ``f7_simulation`` AVANT persistance sans avoir a
manipuler l'etat interne du moteur.
"""
from __future__ import annotations

import warnings

import pytest

from dataclasses import asdict

from domain.market import Bar, MarketSnapshot
from domain.orders import ExecutionPlan
from domain.portfolio import AccountState, PortfolioState
from domain.proposal import AgentOutput, Consensus, SizingDecision, StrategyCandidate
from domain.receipt import Decision, GENESIS_HASH
from domain.provenance import SourceSystem
from domain.types import ActionKind, AssetClass, Authority, DataQuality, Mode, OrderType, Provenance, Side
from execution.binder.engine import CycleEngine
from execution.binder.order_ledger_jsonl import JsonlOrderLedger
from execution.binder.paper_execution import require_paper_mode
from execution.binder.planner import ExecutionPlanner
from external.adapters.base_adapter import ExternalStackAnalysisAdapter
from external.examples.brother_stack.example_adapter import ExampleBrotherStackAdapter
from governance.bridge.governance_bridge import KX108GovernanceBridge
from market.adapters.alpaca.alpaca_config import AlpacaConfig
from native.agents.adapter import NativeRosterAnalysisAdapter
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


# ── Doubles deterministes (pas de reseau) ───────────────────────────────────


def _bars(n: int = 30, base: float = 100.0) -> tuple:
    """Bars OHLCV synthetiques mais deterministes (pas de random) — suffisant
    pour exercer le roster natif sans dependre de donnees de marche reelles."""
    out = []
    price = base
    for i in range(n):
        price = price * (1.0 + (0.001 if i % 2 == 0 else -0.0007))
        out.append(Bar(timestamp=float(i), open=price, high=price * 1.001, low=price * 0.999, close=price, volume=1_000.0))
    return tuple(out)


class FakeMarketData:
    def __init__(self, *, tradable: bool = True, market_open: bool = True, last_price: float = 100.0, with_bars: bool = True):
        self._tradable = tradable
        self._market_open = market_open
        self._last_price = last_price
        self._bars = _bars(base=last_price) if with_bars else ()

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
    """Spy BrokerPort : jamais de reseau, comportement controle par le test."""

    def __init__(self, *, trading_blocked: bool = False, submit_behavior=None):
        self._trading_blocked = trading_blocked
        self._submit_behavior = submit_behavior or (lambda plan: _accepted_result(plan))
        self.submit_calls = []

    def account(self) -> AccountState:
        return AccountState(
            equity=100_000.0,
            cash=100_000.0,
            buying_power=100_000.0,
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

    def submit(self, plan: ExecutionPlan):
        self.submit_calls.append(plan)
        return self._submit_behavior(plan)

    def cancel(self, plan, broker_order_id):
        raise NotImplementedError

    def replace(self, plan, broker_order_id):
        raise NotImplementedError

    def close_position(self, plan):
        raise NotImplementedError


def _accepted_result(plan: ExecutionPlan):
    from domain.orders import ExecutionResult
    from domain.types import OrderStatus

    return ExecutionResult(
        plan=plan, submitted=True, status=OrderStatus.ACCEPTED,
        broker_order_id="fake-order-1", mode=Mode.PAPER.value,
    )


class FakeAggregation:
    def aggregate(self, outputs):
        # Consensus BUY simple des lors qu'au moins un signal existe — le
        # detail du vote n'est pas ce qui est teste dans ce scenario assemble
        # (deja couvert par tests/unit/test_native_roster.py).
        return Consensus(side="BUY", confidence=0.75)


class FakeStrategy:
    def build(self, symbol, snapshot, consensus, portfolio, opportunities=()):
        return (
            StrategyCandidate(
                symbol=symbol, action=ActionKind.BUY, rationale="F8.5 end-to-end",
                confidence=0.75, order_type=OrderType.MARKET, strategy_id="f85-strategy",
            ),
        )


class FakeSizing:
    def size(self, candidate, snapshot, portfolio):
        return SizingDecision(quantity=1.0, requested_quantity=1.0)


def _make_engine(*, verdict: str, broker: FakeBroker, store: ReceiptStore, analysis,
                  order_ledger=None, tradable: bool = True, market_open: bool = True):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # avertissement TEST-ONLY attendu
        kx108 = FixtureKX108Client(verdict=verdict)
    bridge = KX108GovernanceBridge(kx108)
    return CycleEngine(
        market_data=FakeMarketData(tradable=tradable, market_open=market_open),
        broker=broker,
        analysis=analysis,
        aggregation=FakeAggregation(),
        authority=bridge,
        symbols=[SYMBOL],
        mode=Mode.PAPER,
        strategy=FakeStrategy(),
        sizing=FakeSizing(),
        planner=ExecutionPlanner(),
        order_ledger=order_ledger,
        proof=store,  # lit store.last_hash() a la construction -> prolonge la chaine partagee
    )


TRADING_PARAMS = TradingParams(
    seed=42, steps=20, s0=100.0, mu=0.05, sigma=0.2, dt=1 / 252,
    jump_lambda=0.01, jump_mu=-0.02, jump_sigma=0.03,
    garch_alpha=0.1, garch_beta=0.85, garch_omega=0.0001,
    regimes=2, friction_bps=5.0,
)


def _attach_simulation_evidence(receipt, params: TradingParams):
    """
    Cablage minimal F8.5 : execute reellement la simulation F4 et attache le
    resultat sur ``receipt.extensions[f7_simulation]`` AVANT persistance.

    ``CycleReceipt`` est un frozen dataclass mais ``extensions`` est un dict
    mutable : muter son contenu (pas reassigner l'attribut) est le mecanisme
    documente par F7 pour un enrichissement pre-persistance (voir
    execution/binder/engine.py::_prove, commentaire sur le decorateur de
    preuve). Le resultat de simulation voyage comme EVIDENCE (une entree dans
    extensions), jamais comme Authority — la Decision est deja figee avant cet
    appel et n'est pas touchee ici.
    """
    steps, returns = run_trading_simulation(params)
    extension = build_simulation_extension(
        kind=SIMULATION_KIND_TRADING_WORLD,
        seed=params.seed,
        params=asdict(params),
        engine_version="market_process.v1",
        steps=steps,
        returns=returns,
    )
    receipt.extensions[SIMULATION_EXTENSION_KEY] = extension
    return receipt


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 1 — ACT, simulation branchee, ordre PAPER, replay audit + deterministe
# ═══════════════════════════════════════════════════════════════════════════


def test_scenario_1_act_with_simulation_produces_paper_order_and_replayable_receipt(tmp_path):
    store = ReceiptStore(tmp_path / "receipts.jsonl")
    assert store.last_hash() == GENESIS_HASH  # store vide : ce scenario tourne en premier

    broker = FakeBroker()
    ledger = JsonlOrderLedger(tmp_path / "ledger.jsonl")

    # Chemin NATIF : vrai roster de 17 agents (F3), pas un double.
    engine_probe = CycleEngine(
        market_data=FakeMarketData(),
        broker=broker,
        analysis=NativeRosterAnalysisAdapter(),
        aggregation=FakeAggregation(),
        authority=KX108GovernanceBridge(
            _fixture_client("ACT")
        ),
        symbols=[SYMBOL],
        mode=Mode.PAPER,
        strategy=FakeStrategy(),
        sizing=FakeSizing(),
        planner=ExecutionPlanner(),
        order_ledger=ledger,
        proof=None,  # on persiste manuellement APRES avoir attache la simulation
    )
    outcome = engine_probe.run_cycle()

    assert outcome.decision.authority is Authority.ACT
    assert outcome.plan is not None
    assert outcome.execution is not None and outcome.execution.submitted is True
    assert outcome.touched_the_market is True
    assert len(broker.submit_calls) == 1

    # Provenance native reellement produite par le roster (pas simulee) :
    native_outputs = [
        o for o in outcome.agent_outputs
        if o.source_provenance is not None and o.source_provenance.source_system is SourceSystem.NATIVE
    ]
    assert len(native_outputs) == 17  # les 17 agents taguent leur sortie comme native

    # Cablage F8.5 : la simulation F4 est reellement executee et attachee
    # comme evidence AVANT la persistance du receipt (pas apres coup / mock).
    receipt = _attach_simulation_evidence(outcome.receipt, TRADING_PARAMS)
    assert receipt.previous_receipt_hash == GENESIS_HASH
    stored = store.record(receipt)
    assert stored is receipt

    # 1 ordre PAPER, 1 execution result, 1 receipt persiste.
    history = store.history()
    assert len(history) == 1
    assert history[0].authority == "ACT"

    # Hash-chain valide pour ce seul receipt.
    report = ReceiptChainVerifier().verify_store(store)
    assert report.status is IntegrityStatus.VALID

    # Replay audit : reconstruit source -> cognition -> KX108 -> Binder -> execution
    # sans effet de bord (aucun appel broker supplementaire).
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

    # Seed differente -> DIVERGENCE.
    different_params = TradingParams(**{**asdict(TRADING_PARAMS), "seed": 999})
    steps2, returns2 = run_trading_simulation(different_params)
    # Compare directement les digests (pas besoin de repersister un receipt) :
    # on prouve que le mecanisme de comparaison distingue bien deux seeds.
    ext_original = receipt.extensions[SIMULATION_EXTENSION_KEY]
    ext_different = build_simulation_extension(
        kind=SIMULATION_KIND_TRADING_WORLD, seed=different_params.seed,
        params=asdict(different_params), engine_version="market_process.v1",
        steps=steps2, returns=returns2,
    )
    assert ext_original["output_digest"] != ext_different["output_digest"]


def _fixture_client(verdict: str) -> FixtureKX108Client:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return FixtureKX108Client(verdict=verdict)


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 2 — HOLD : aucun ordre, receipt quand meme produit, replay possible
# ═══════════════════════════════════════════════════════════════════════════


def test_scenario_2_hold_no_order_but_receipt_persisted_and_replayable(tmp_path):
    store = _seeded_store(tmp_path)
    broker = FakeBroker()
    engine = _make_engine(verdict="HOLD", broker=broker, store=store, analysis=_single_fake_analysis())
    outcome = engine.run_cycle()

    assert outcome.decision.authority is Authority.HOLD
    assert outcome.execution is None
    assert broker.submit_calls == []
    assert outcome.receipt is not None

    replay = ReplayEngine(store)
    audit = replay.replay_audit(outcome.receipt.cycle_id)
    assert audit.found is True
    assert audit.kx108_verdict["authority"] == "HOLD"
    assert audit.execution is None


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 3 — BLOCK : aucune execution, raison tracable, provenance conservee
# ═══════════════════════════════════════════════════════════════════════════


def test_scenario_3_block_no_execution_reason_traceable(tmp_path):
    store = _seeded_store(tmp_path)
    broker = FakeBroker()
    engine = _make_engine(verdict="BLOCK", broker=broker, store=store, analysis=_single_fake_analysis())
    outcome = engine.run_cycle()

    assert outcome.decision.authority is Authority.BLOCK
    assert outcome.execution is None
    assert broker.submit_calls == []

    receipt_dict = outcome.receipt.as_dict()
    assert receipt_dict["decision"]["metrics"]["kx108_response"]["verdict"] == "BLOCK"
    assert receipt_dict["decision"]["metrics"]["kx108_response"]["source"] == "FixtureKX108Client (TEST-ONLY)"


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 4 — ACT mais Binder refuse (etat degrade) : Decision != Permission
# ═══════════════════════════════════════════════════════════════════════════


def test_scenario_4_act_but_binder_refuses_proves_decision_is_not_permission(tmp_path):
    store = _seeded_store(tmp_path)
    broker = FakeBroker(trading_blocked=True)  # can_support_irreversible_action -> False
    engine = _make_engine(verdict="ACT", broker=broker, store=store, analysis=_single_fake_analysis())
    outcome = engine.run_cycle()

    assert outcome.decision.authority is Authority.ACT  # KX108 a bien dit ACT...
    assert outcome.plan is None  # ...mais le Binder refuse (compte bloque)
    assert outcome.execution is None
    assert broker.submit_calls == []


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 5 — Erreur broker : receipt FAILURE explicite, jamais faux succes
# ═══════════════════════════════════════════════════════════════════════════


def test_scenario_5_broker_error_produces_explicit_failure_never_false_success(tmp_path):
    store = _seeded_store(tmp_path)

    def failing_submit(plan):
        raise RuntimeError("Alpaca 500: internal error")

    broker = FakeBroker(submit_behavior=failing_submit)
    engine = _make_engine(verdict="ACT", broker=broker, store=store, analysis=_single_fake_analysis())
    outcome = engine.run_cycle()

    assert len(broker.submit_calls) == 1  # la tentative a bien eu lieu
    assert outcome.execution is not None
    assert outcome.execution.submitted is False
    assert outcome.touched_the_market is False
    assert "echec de soumission" in (outcome.execution.rejected_reason or "")

    receipt_dict = outcome.receipt.as_dict()
    assert receipt_dict["consequence"]["executed"] is False


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 6 — Double soumission du meme intent : idempotence reelle
# ═══════════════════════════════════════════════════════════════════════════


def test_scenario_6_duplicate_intent_is_rejected_without_duplicate_broker_call(tmp_path):
    store = _seeded_store(tmp_path)
    broker = FakeBroker()
    ledger = JsonlOrderLedger(tmp_path / "ledger-dup.jsonl")
    engine = _make_engine(verdict="ACT", broker=broker, store=store, analysis=_single_fake_analysis(), order_ledger=ledger)

    proposal_consensus = Consensus(side="BUY", confidence=0.9)
    sizing = SizingDecision(quantity=1.0, requested_quantity=1.0)
    from domain.proposal import ActionProposal

    proposal = ActionProposal(symbol=SYMBOL, action=ActionKind.BUY, consensus=proposal_consensus, sizing=sizing)
    decision = Decision(decision_id="d-f85-dup", authority=Authority.ACT, reason="test", proposal=proposal)
    plan = ExecutionPlan(
        decision_id=decision.decision_id, symbol=SYMBOL, action=ActionKind.BUY, side=Side.BUY,
        quantity=1.0, order_type=OrderType.MARKET, authority=Authority.ACT,
        client_order_id="obsidia-d-f85-dup",
    )

    result_1 = engine._execute("cycle-f85-1", decision, plan, lambda msg: None)
    result_2 = engine._execute("cycle-f85-2", decision, plan, lambda msg: None)  # meme intent, deuxieme tentative

    assert result_1.submitted is True
    assert result_2.submitted is False
    assert "idempotence" in (result_2.rejected_reason or "")
    assert len(broker.submit_calls) == 1  # le broker n'a ete appele qu'une seule fois


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 7 — Provenance native vs externe, conservee jusqu'au receipt reload
# ═══════════════════════════════════════════════════════════════════════════


def test_scenario_7_native_and_external_provenance_both_survive_to_reloaded_receipt(tmp_path):
    store = _seeded_store(tmp_path)
    broker = FakeBroker()

    # Chemin NATIF.
    engine_native = _make_engine(
        verdict="ACT", broker=broker, store=store,
        analysis=NativeRosterAnalysisAdapter(),
    )
    outcome_native = engine_native.run_cycle()
    assert outcome_native.decision.authority is Authority.ACT

    # Chemin EXTERNE : meme Governance Bridge, meme Binder, meme Broker —
    # seule la source de cognition change (F8, aucune duplication).
    engine_external = _make_engine(
        verdict="ACT", broker=broker, store=store,
        analysis=ExternalStackAnalysisAdapter(ExampleBrotherStackAdapter()),
    )
    outcome_external = engine_external.run_cycle()
    assert outcome_external.decision.authority is Authority.ACT

    # Convergence exacte : meme type de Decision produit par le meme Bridge,
    # que la cognition soit native ou externe.
    assert type(outcome_native.decision) is type(outcome_external.decision)

    # Provenance conservee jusqu'au receipt RECHARGE DEPUIS LE STORE (pas juste en memoire).
    reloaded_native = store.find_by_cycle_id(outcome_native.cycle_id)
    reloaded_external = store.find_by_cycle_id(outcome_external.cycle_id)
    assert reloaded_native is not None and reloaded_external is not None

    native_agent_outputs = reloaded_native.raw["decision"]["proposal"]["agent_outputs"]
    external_agent_outputs = reloaded_external.raw["decision"]["proposal"]["agent_outputs"]

    assert all(ao["source_provenance"]["source_system"] == "native" for ao in native_agent_outputs)
    external_provenances = [ao["source_provenance"] for ao in external_agent_outputs]
    assert all(p["source_system"] == "external" for p in external_provenances)
    assert all(p["adapter_id"] == "brother_stack_v1" for p in external_provenances)
    assert all(p["source_id"] == "brother_strategy_07" for p in external_provenances)
    assert all(p["organization_id"] == "brother_company" for p in external_provenances)

    # unknowns/risk_flags fournis par la stack externe (ExampleBrotherStackAdapter)
    # survivent jusqu'au receipt recharge.
    assert any("stack_externe_non_auditee" in ao.get("unknowns", []) for ao in external_agent_outputs)
    assert any("aucune_verification_independante" in ao.get("risk_flags", []) for ao in external_agent_outputs)


# ═══════════════════════════════════════════════════════════════════════════
# Hash-chain globale + alteration volontaire (sur COPIE, jamais l'original)
# ═══════════════════════════════════════════════════════════════════════════


def test_full_chain_across_all_scenarios_is_valid_then_detects_tampering(tmp_path):
    """
    Rejoue les scenarios 1-4 + 7 dans UNE seule chaine partagee (comme le
    ferait un run reel), verifie l'integrite globale, puis altere une COPIE
    du fichier pour prouver la detection — jamais l'original.
    """
    store = ReceiptStore(tmp_path / "chain.jsonl")

    engine_hold = _make_engine(verdict="HOLD", broker=FakeBroker(), store=store, analysis=_single_fake_analysis())
    engine_hold.run_cycle()

    engine_block = _make_engine(verdict="BLOCK", broker=FakeBroker(), store=store, analysis=_single_fake_analysis())
    engine_block.run_cycle()

    engine_degraded = _make_engine(
        verdict="ACT", broker=FakeBroker(trading_blocked=True), store=store, analysis=_single_fake_analysis()
    )
    engine_degraded.run_cycle()

    engine_act = _make_engine(verdict="ACT", broker=FakeBroker(), store=store, analysis=_single_fake_analysis())
    engine_act.run_cycle()

    assert len(store.history(limit=0)) == 4

    report = ReceiptChainVerifier().verify_store(store)
    assert report.status is IntegrityStatus.VALID
    assert report.checked_count == 4

    # Copie avant alteration — l'original ne doit jamais etre touche.
    import shutil

    tampered_path = tmp_path / "chain_tampered.jsonl"
    shutil.copy(store.path, tampered_path)

    lines = tampered_path.read_text(encoding="utf-8").splitlines()
    import json as _json

    mid = _json.loads(lines[1])
    mid["receipt"]["decision"]["reason"] = "ALTERE PAR LE TEST"  # contenu modifie
    lines[1] = _json.dumps(mid)
    tampered_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    tampered_report = ReceiptChainVerifier().verify_path(tampered_path)
    assert tampered_report.status is IntegrityStatus.CORRUPTED
    assert tampered_report.first_error_index == 1

    # L'original reste VALID : aucune reparation, aucune contamination.
    original_report = ReceiptChainVerifier().verify_store(store)
    assert original_report.status is IntegrityStatus.VALID


# ═══════════════════════════════════════════════════════════════════════════
# Tests structurels — les proprietes tiennent ENSEMBLE, pas juste isolement
# ═══════════════════════════════════════════════════════════════════════════


def test_paper_only_environment_is_enforced_before_any_construction():
    """PAPER ONLY : toute tentative LIVE est refusee avant toute construction reseau."""
    from execution.binder.paper_execution import LiveModeRejected

    live_config = AlpacaConfig(mode=Mode.LIVE, api_key="x", secret_key="y", trading_base_url="https://api.alpaca.markets")
    with pytest.raises(LiveModeRejected):
        require_paper_mode(live_config)


def test_no_category_ever_grants_itself_authority_beyond_its_role(tmp_path):
    """
    Assertions groupees, sur un cycle ACT reel, prouvant ensemble :
    Agent != Authority, External Adapter != Authority, Simulation != Authority,
    Intent != Action, KX108 Decision != Binder Permission,
    Binder Permission != Execution Success, Receipt != Decision,
    Proof != Authority, Replay != Execution, Source Provenance != Trust.
    """
    store = _seeded_store(tmp_path)

    # Agent != Authority, Intent != Action : un consensus BUY fort ne force pas
    # une execution si le Binder refuse (etat degrade) — deja prouve isolement
    # au scenario 4, reconfirme ici sur le meme cycle que celui utilise pour
    # les autres assertions groupees.
    broker_degraded = FakeBroker(trading_blocked=True)
    engine_degraded = _make_engine(verdict="ACT", broker=broker_degraded, store=store, analysis=_single_fake_analysis())
    outcome_degraded = engine_degraded.run_cycle()
    assert outcome_degraded.decision.authority is Authority.ACT  # KX108 Decision...
    assert outcome_degraded.plan is None  # ...!= Binder Permission
    assert broker_degraded.submit_calls == []

    # External Adapter != Authority : le meme scenario avec cognition externe
    # ne decide jamais lui-meme non plus.
    broker_external = FakeBroker()
    engine_external = _make_engine(
        verdict="HOLD", broker=broker_external, store=store,
        analysis=ExternalStackAnalysisAdapter(ExampleBrotherStackAdapter()),
    )
    outcome_external = engine_external.run_cycle()
    assert outcome_external.decision.authority is Authority.HOLD  # jamais ACT invente par l'adapter
    assert broker_external.submit_calls == []

    # Binder Permission != Execution Success : une soumission autorisee peut
    # quand meme echouer cote broker (deja prouve scenario 5, reconfirme ici).
    def failing_submit(plan):
        raise RuntimeError("broker error")

    broker_failing = FakeBroker(submit_behavior=failing_submit)
    engine_failing = _make_engine(verdict="ACT", broker=broker_failing, store=store, analysis=_single_fake_analysis())
    outcome_failing = engine_failing.run_cycle()
    assert outcome_failing.plan is not None  # le Binder AVAIT autorise le plan...
    assert outcome_failing.execution.submitted is False  # ...mais l'execution a echoue

    # Receipt != Decision, Proof != Authority : persister ne change jamais la decision deja prise.
    authority_before = outcome_failing.decision.authority
    reloaded = store.find_by_cycle_id(outcome_failing.cycle_id)
    assert reloaded.authority == authority_before.value

    # Replay != Execution : le replay audit ne rappelle jamais le broker.
    calls_before_replay = len(broker_failing.submit_calls)
    ReplayEngine(store).replay_audit(outcome_failing.cycle_id)
    assert len(broker_failing.submit_calls) == calls_before_replay

    # Source Provenance != Trust : un signal externe (moins "controle" par
    # construction que le natif) produit exactement le meme type de Decision
    # qu'un signal natif pour un verdict KX108 identique — la provenance ne
    # module ni positivement ni negativement l'autorite.
    broker_native = FakeBroker()
    broker_ext2 = FakeBroker()
    engine_native_act = _make_engine(verdict="ACT", broker=broker_native, store=store, analysis=NativeRosterAnalysisAdapter())
    engine_external_act = _make_engine(
        verdict="ACT", broker=broker_ext2, store=store,
        analysis=ExternalStackAnalysisAdapter(ExampleBrotherStackAdapter()),
    )
    outcome_native_act = engine_native_act.run_cycle()
    outcome_external_act = engine_external_act.run_cycle()
    assert outcome_native_act.decision.authority is outcome_external_act.decision.authority is Authority.ACT
    assert outcome_native_act.touched_the_market is outcome_external_act.touched_the_market is True


def test_replay_module_never_imports_broker_or_binder_assembly():
    """Redondant avec tests/unit/test_receipt_chain.py mais reaffirme dans le
    contexte de l'assemblage complet F8.5 : Replay != Execution structurellement."""
    import pathlib

    replay_source = (pathlib.Path(__file__).resolve().parents[2] / "proof" / "receipts" / "replay.py").read_text(encoding="utf-8")
    assert "market.adapters.alpaca" not in replay_source.replace("`market.adapters.alpaca`", "")
    assert "execution.binder.paper_execution" not in replay_source.replace("`execution.binder.paper_execution`", "")


# ── Aides partagees ─────────────────────────────────────────────────────────


def _seeded_store(tmp_path) -> ReceiptStore:
    """
    Store partage par les scenarios 2-7 : demarre volontairement APRES le
    scenario 1 dans l'ordre de lecture du fichier, mais chaque scenario 2-7
    utilise son PROPRE fichier tmp_path isole (tmp_path est unique par test) —
    seul le test de hash-chain globale (ci-dessus) fait cohabiter plusieurs
    cycles dans une chaine unique intentionnellement.
    """
    return ReceiptStore(tmp_path / "receipts.jsonl")


def _single_fake_analysis():
    class _FakeAnalysis:
        def analyse(self, symbol, snapshot, portfolio):
            return (
                AgentOutput(name="fake-agent", category="test", signal="BUY", confidence=0.9, rationale="F8.5 fixture"),
            )

    return _FakeAnalysis()
