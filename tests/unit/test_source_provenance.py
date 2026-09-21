"""
F7.5 — Source Provenance Closure : la provenance d'un signal (natif, externe,
humain, replay, simulation) doit traverser sans perte jusqu'au receipt, et ne
JAMAIS influencer Decision.authority ni l'acces Binder/Broker.

Chaque test verifie un chemin reel :
    Source -> AgentOutput -> ActionProposal -> Decision (Governance Bridge)
           -> CycleReceipt -> ReceiptStore (JSONL) -> reload
"""
from __future__ import annotations

import time
import warnings

import pytest

from domain.market import MarketSnapshot
from domain.orders import ExecutionPlan, ExecutionResult
from domain.portfolio import AccountState, PortfolioState
from domain.proposal import ActionProposal, AgentOutput, Consensus, SizingDecision, StrategyCandidate
from domain.provenance import SourceKind, SourceProvenance, SourceSystem
from domain.types import ActionKind, AssetClass, Authority, DataQuality, Mode, OrderStatus, OrderType, Provenance
from execution.binder.engine import CycleEngine
from execution.binder.planner import ExecutionPlanner
from governance.bridge.governance_bridge import KX108GovernanceBridge
from native.agents.adapter import agent_vote_to_agent_output
from native.agents.contracts import TradingState
from native.agents.domains.trading_agents import MarketDataAgent
from proof.receipts.receipt_store import ReceiptStore
from proof.receipts.replay import ReplayEngine
from tests.test_support.kx108_fixtures import FixtureKX108Client

SYMBOL = "AAPL"


# ── Fixtures partagees (memes conventions que tests/unit/test_receipt_chain.py) ──


class FakeMarketData:
    def snapshot(self, symbol):
        return self.snapshots([symbol])[symbol]

    def snapshots(self, symbols):
        return {
            s: MarketSnapshot(
                symbol=s,
                asset_class=AssetClass.EQUITY,
                last_price=100.0,
                provenance=Provenance(source="fake", fetched_at=0.0, quality=DataQuality.LIVE, mode=Mode.PAPER),
                tradable=True,
                market_open=True,
            )
            for s in symbols
        }

    def history(self, symbol, limit=200):
        return ()

    def context(self):
        return None


class FakeBroker:
    def account(self):
        return AccountState(
            equity=100_000.0, cash=100_000.0, buying_power=100_000.0,
            provenance=Provenance(source="fake", fetched_at=0.0, quality=DataQuality.LIVE, mode=Mode.PAPER),
            trading_blocked=False,
        )

    def positions(self):
        return ()

    def open_orders(self):
        return ()

    def portfolio(self):
        return PortfolioState(account=self.account())

    def submit(self, plan):
        return ExecutionResult(plan=plan, submitted=True, status=OrderStatus.ACCEPTED,
                                broker_order_id="fake-order-1", mode=Mode.PAPER.value)

    def close_position(self, plan):
        raise NotImplementedError


class _StaticAnalysis:
    """Retourne exactement les AgentOutput fournis a la construction — permet
    a chaque test de choisir precisement la provenance a faire circuler."""

    def __init__(self, outputs):
        self._outputs = tuple(outputs)

    def analyse(self, symbol, snapshot, portfolio):
        return self._outputs


class FakeAggregation:
    def aggregate(self, outputs):
        return Consensus(side="BUY", confidence=0.9)


class FakeStrategy:
    def build(self, symbol, snapshot, consensus, portfolio, opportunities=()):
        return (
            StrategyCandidate(symbol=symbol, action=ActionKind.BUY, rationale="fixture F7.5",
                               confidence=0.9, order_type=OrderType.MARKET, strategy_id="fixture-strategy"),
        )


class FakeSizing:
    def size(self, candidate, snapshot, portfolio):
        return SizingDecision(quantity=1.0, requested_quantity=1.0)


def _make_engine(*, verdict: str, outputs, proof=None):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        kx108 = FixtureKX108Client(verdict=verdict)
    bridge = KX108GovernanceBridge(kx108)
    return CycleEngine(
        market_data=FakeMarketData(),
        broker=FakeBroker(),
        analysis=_StaticAnalysis(outputs),
        aggregation=FakeAggregation(),
        authority=bridge,
        symbols=[SYMBOL],
        mode=Mode.PAPER,
        strategy=FakeStrategy(),
        sizing=FakeSizing(),
        planner=ExecutionPlanner(),
        proof=proof,
    )


def _agent_outputs_of(receipt) -> list:
    return receipt.as_dict()["decision"]["proposal"]["agent_outputs"]


# ── 1. Agent natif -> provenance native conservee jusqu'au receipt ──────────


def test_native_agent_provenance_survives_to_receipt(tmp_path):
    state = TradingState(symbol=SYMBOL, prices=[100.0, 101.5], highs=[101.0, 102.0],
                          lows=[99.0, 100.0], volumes=[1000.0, 1200.0])
    vote = MarketDataAgent().evaluate(state)
    native_output = agent_vote_to_agent_output(vote)
    assert native_output.source_provenance.source_system is SourceSystem.NATIVE

    store = ReceiptStore(tmp_path / "receipts.jsonl")
    engine = _make_engine(verdict="ACT", outputs=[native_output], proof=store)
    outcome = engine.run_cycle()

    stored = store.read(outcome.receipt.decision.decision_id)
    provenance = _agent_outputs_of(outcome.receipt)[0]["source_provenance"]
    assert provenance is not None
    assert provenance["source_system"] == "native"
    assert provenance["source_kind"] == "agent"
    assert provenance["source_id"] == "MarketDataAgent"
    # Et depuis le disque, pas seulement l'objet en memoire :
    assert stored.raw["decision"]["proposal"]["agent_outputs"][0]["source_provenance"] == provenance


# ── 2. Signal externe -> provenance external conservee ──────────────────────


def test_external_signal_provenance_survives_to_receipt(tmp_path):
    provenance = SourceProvenance.for_external_signal(
        source_id="brother_strategy_07",
        source_kind=SourceKind.RULE,
        adapter_id="brother_stack_v1",
        organization_id="brother_company",
    )
    external_output = AgentOutput(
        name="brother_strategy_07", category="EXTERNAL", signal="BUY", confidence=0.6,
        rationale="external stack signal", source_provenance=provenance,
    )

    store = ReceiptStore(tmp_path / "receipts.jsonl")
    engine = _make_engine(verdict="ACT", outputs=[external_output], proof=store)
    outcome = engine.run_cycle()

    persisted = _agent_outputs_of(outcome.receipt)[0]["source_provenance"]
    assert persisted["source_system"] == "external"
    assert persisted["adapter_id"] == "brother_stack_v1"
    assert persisted["organization_id"] == "brother_company"


# ── 3. Source humaine -> reste human, jamais convertie en native ───────────


def test_human_source_provenance_is_never_converted_to_native(tmp_path):
    human_provenance = SourceProvenance(
        source_system=SourceSystem.HUMAN, source_kind=SourceKind.OPERATOR, source_id="operator-42",
    )
    human_output = AgentOutput(
        name="manual-override", category="HUMAN", signal="HOLD", confidence=1.0,
        rationale="operateur humain", source_provenance=human_provenance,
    )

    store = ReceiptStore(tmp_path / "receipts.jsonl")
    engine = _make_engine(verdict="HOLD", outputs=[human_output], proof=store)
    outcome = engine.run_cycle()

    persisted = _agent_outputs_of(outcome.receipt)[0]["source_provenance"]
    assert persisted["source_system"] == "human"
    assert persisted["source_system"] != "native"


# ── 4. Adapter externe -> source_id ET adapter_id tous deux conserves ──────


def test_external_adapter_preserves_source_id_and_adapter_id_together(tmp_path):
    provenance = SourceProvenance.for_external_signal(
        source_id="original-model-9",
        source_kind=SourceKind.MODEL,
        adapter_id="acme-adapter-v2",
        original_event_id="evt-12345",
    )
    output = AgentOutput(
        name="original-model-9", category="EXTERNAL", signal="SELL", confidence=0.4,
        rationale="modele externe", source_provenance=provenance,
    )

    store = ReceiptStore(tmp_path / "receipts.jsonl")
    engine = _make_engine(verdict="HOLD", outputs=[output], proof=store)
    outcome = engine.run_cycle()

    persisted = _agent_outputs_of(outcome.receipt)[0]["source_provenance"]
    assert persisted["source_id"] == "original-model-9"
    assert persisted["adapter_id"] == "acme-adapter-v2"
    assert persisted["original_event_id"] == "evt-12345"


# ── 5. Replay -> provenance originale conservee, contexte replay distinguable ──


def test_replay_audit_preserves_original_provenance_unchanged(tmp_path):
    provenance = SourceProvenance.for_external_signal(
        source_id="ext-agent-1", source_kind=SourceKind.API, adapter_id="ext-adapter",
    )
    output = AgentOutput(
        name="ext-agent-1", category="EXTERNAL", signal="BUY", confidence=0.5,
        rationale="pour replay", source_provenance=provenance,
    )
    store = ReceiptStore(tmp_path / "receipts.jsonl")
    engine = _make_engine(verdict="ACT", outputs=[output], proof=store)
    outcome = engine.run_cycle()

    replay = ReplayEngine(store)
    result = replay.replay_audit(outcome.receipt.cycle_id)

    assert result.found is True
    replayed_provenance = result.proposed["agent_outputs"][0]["source_provenance"]
    original_provenance = _agent_outputs_of(outcome.receipt)[0]["source_provenance"]
    # Le replay audit ne fait que relire : la provenance originale n'est ni
    # perdue, ni reecrite en "native" ou en "replay" par la simple lecture.
    assert replayed_provenance == original_provenance
    assert replayed_provenance["source_system"] == "external"


def test_source_provenance_for_replay_of_is_distinguishable_from_original():
    """
    `for_replay_of` (constructeur dedie, non branche dans replay.py — voir
    docstring de domain/provenance.py) : si un futur mecanisme regenere
    activement un signal pendant un replay, le resultat ne doit jamais se
    faire passer pour une nouvelle observation native, meme si l'original
    l'etait.
    """
    original = SourceProvenance.for_native_agent("MarketDataAgent", observed_at=1000.0)
    replayed = SourceProvenance.for_replay_of(original, replayed_at=2000.0)

    assert original.source_system is SourceSystem.NATIVE
    assert replayed.source_system is SourceSystem.REPLAY
    assert replayed.source_system != original.source_system
    assert replayed.source_id == original.source_id
    assert replayed.observed_at == original.observed_at  # preservee
    assert replayed.ingested_at == 2000.0  # horodatage du replay, distinct


# ── 6. Absence de provenance -> None explicite, jamais devine ──────────────


def test_missing_source_provenance_is_explicit_none_not_invented(tmp_path):
    output_without_provenance = AgentOutput(
        name="legacy-caller", category="TEST", signal="HOLD", confidence=0.5, rationale="pre-F7.5",
    )
    assert output_without_provenance.source_provenance is None
    assert output_without_provenance.as_dict()["source_provenance"] is None

    store = ReceiptStore(tmp_path / "receipts.jsonl")
    engine = _make_engine(verdict="HOLD", outputs=[output_without_provenance], proof=store)
    outcome = engine.run_cycle()

    persisted = _agent_outputs_of(outcome.receipt)[0]["source_provenance"]
    assert persisted is None  # jamais une valeur par defaut devinee (ex: "native")

    # Reconstruction explicite depuis un dict absent : None, pas une erreur.
    assert SourceProvenance.from_dict(None) is None


# ── 7. Provenance ne modifie jamais Decision.authority ─────────────────────


@pytest.mark.parametrize("verdict", ["ACT", "HOLD", "BLOCK"])
def test_source_provenance_never_changes_decision_authority(tmp_path, verdict):
    native_provenance = SourceProvenance.for_native_agent("agent-x")
    external_provenance = SourceProvenance.for_external_signal(
        source_id="agent-x", source_kind=SourceKind.AGENT, adapter_id="whatever",
    )

    def _output(provenance):
        return AgentOutput(
            name="agent-x", category="TRADING", signal="BUY", confidence=0.9,
            rationale="identique sauf provenance", source_provenance=provenance,
        )

    store_a = ReceiptStore(tmp_path / "a.jsonl")
    store_b = ReceiptStore(tmp_path / "b.jsonl")
    outcome_native = _make_engine(verdict=verdict, outputs=[_output(native_provenance)], proof=store_a).run_cycle()
    outcome_external = _make_engine(verdict=verdict, outputs=[_output(external_provenance)], proof=store_b).run_cycle()

    assert outcome_native.receipt.decision.authority == outcome_external.receipt.decision.authority
    assert outcome_native.receipt.decision.authority == Authority.from_legacy(verdict)


# ── 8. Provenance ne permet jamais d'appeler Binder/Broker ─────────────────


def test_source_provenance_module_has_no_execution_or_broker_access():
    import pathlib

    source = pathlib.Path("domain/provenance.py").read_text(encoding="utf-8")
    forbidden = ("execution.binder", "market.adapters.alpaca", "import execution", "import market")
    for token in forbidden:
        assert token not in source, f"domain/provenance.py ne doit jamais referencer {token!r}"


# ── 9. Serialisation JSONL + reload -> provenance identique bit pour bit ───


def test_source_provenance_survives_jsonl_roundtrip_fully_populated(tmp_path):
    provenance = SourceProvenance(
        source_system=SourceSystem.EXTERNAL,
        source_kind=SourceKind.ADAPTER,
        source_id="full-source",
        adapter_id="full-adapter",
        organization_id="full-org",
        original_event_id="full-event",
        observed_at=123.456,
        ingested_at=789.012,
    )
    output = AgentOutput(
        name="full-source", category="EXTERNAL", signal="BUY", confidence=0.5,
        rationale="roundtrip complet", source_provenance=provenance,
    )
    store = ReceiptStore(tmp_path / "receipts.jsonl")
    outcome = _make_engine(verdict="ACT", outputs=[output], proof=store).run_cycle()

    reloaded_store = ReceiptStore(tmp_path / "receipts.jsonl")  # nouvelle instance = "restart"
    stored = reloaded_store.read(outcome.receipt.decision.decision_id)
    reloaded_dict = stored.raw["decision"]["proposal"]["agent_outputs"][0]["source_provenance"]

    assert reloaded_dict == provenance.as_dict()
    reconstructed = SourceProvenance.from_dict(reloaded_dict)
    assert reconstructed == provenance


# ── 10. receipt_schema_version reste compatible (pas de bump necessaire) ──


def test_receipt_schema_version_unchanged_and_old_format_still_readable(tmp_path):
    from domain.receipt import RECEIPT_SCHEMA_VERSION

    # F7.5 est un ajout additif (champ optionnel a None) : la version du
    # schema documente de receipt (domain/receipt.py) n'a pas besoin d'etre
    # incrementee. Verifie que la constante n'a pas change...
    assert RECEIPT_SCHEMA_VERSION == "receipt.v1"

    # ...et qu'un receipt dont les agent_outputs n'ont PAS de cle
    # "source_provenance" (format pre-F7.5) reste lisible sans erreur : on
    # simule ce cas en retirant la cle a la main avant persistance, comme le
    # ferait une ligne ecrite par une version anterieure du code.
    output = AgentOutput(
        name="legacy", category="TEST", signal="HOLD", confidence=0.5, rationale="pre-F7.5",
    )
    store = ReceiptStore(tmp_path / "receipts.jsonl")
    outcome = _make_engine(verdict="HOLD", outputs=[output], proof=store).run_cycle()

    raw_line = store.all_raw_lines()[0]
    del raw_line["receipt"]["decision"]["proposal"]["agent_outputs"][0]["source_provenance"]
    rewritten = __import__("json").dumps(raw_line)
    (tmp_path / "receipts.jsonl").write_text(rewritten + "\n", encoding="utf-8")

    reloaded = ReceiptStore(tmp_path / "receipts.jsonl")
    stored = reloaded.read(outcome.receipt.decision.decision_id)
    assert stored is not None  # pas d'exception : cle manquante = lecture normale
    agent_output = stored.raw["decision"]["proposal"]["agent_outputs"][0]
    assert agent_output.get("source_provenance") is None
