"""
F8 — External Stack Adapter : une stack Trading tierce doit produire le MEME
Canonical Contract que le chemin natif, avec uniquement une provenance
differente. Aucune deuxieme architecture metier, aucune autorite parallele.

    ARBITRARY EXTERNAL STACK -> validation -> normalization
        -> provenance preservation -> Canonical Domain Contract
        -> same Governance Bridge (F5) -> same KX108
"""
from __future__ import annotations

import pathlib
import time
import warnings

import pytest

from domain.proposal import ActionProposal, AgentOutput, Consensus, SizingDecision
from domain.state import TradingDomainState
from domain.types import ActionKind, Authority, Mode, OrderType
from external.adapters.base_adapter import ExternalStackAnalysisAdapter
from external.contracts.external_signal import ExternalSignal, InvalidExternalSignal
from external.examples.brother_stack.example_adapter import ExampleBrotherStackAdapter
from external.normalization.normalizer import normalize_external_signal
from governance.bridge.governance_bridge import KX108GovernanceBridge
from governance.bridge.kx108_client import StaticKX108Client
from native.agents.adapter import agent_vote_to_agent_output
from native.agents.contracts import TradingState
from native.agents.domains.trading_agents import MarketDataAgent


def _proposal_with(agent_output: AgentOutput) -> ActionProposal:
    return ActionProposal(
        symbol="AAPL",
        action=ActionKind.BUY,
        consensus=Consensus(side="BUY", confidence=agent_output.confidence),
        sizing=SizingDecision(quantity=1.0, requested_quantity=1.0),
        agent_outputs=(agent_output,),
    )


# ── 1. ExternalSignal valide -> Canonical Contract, source_system=external ──


def test_valid_external_signal_normalizes_with_external_provenance_preserved():
    signal = ExternalSignal.from_raw_payload(
        {
            "source_id": "brother_strategy_07",
            "organization_id": "brother_company",
            "symbol": "AAPL",
            "signal": "BUY",
            "confidence": 0.6,
            "rationale": "signal externe valide",
        }
    )
    output = normalize_external_signal(signal, adapter_id="brother_stack_v1")

    assert output.source_provenance.source_system.value == "external"
    assert output.source_provenance.source_id == "brother_strategy_07"
    assert output.source_provenance.adapter_id == "brother_stack_v1"
    assert output.signal == "BUY"
    assert output.confidence == pytest.approx(0.6)


# ── 2. Champs manquants -> rejet explicite, aucune valeur inventee ──────────


@pytest.mark.parametrize(
    "missing_field",
    ["source_id", "organization_id", "symbol", "signal", "confidence", "rationale"],
)
def test_external_signal_with_missing_field_is_rejected_explicitly(missing_field):
    payload = {
        "source_id": "x", "organization_id": "org", "symbol": "AAPL", "signal": "BUY",
        "confidence": 0.5, "rationale": "test",
    }
    del payload[missing_field]
    with pytest.raises(InvalidExternalSignal):
        ExternalSignal.from_raw_payload(payload)


def test_external_signal_with_non_numeric_confidence_is_rejected():
    payload = {
        "source_id": "x", "organization_id": "org", "symbol": "AAPL", "signal": "BUY",
        "confidence": "not-a-number", "rationale": "test",
    }
    with pytest.raises(InvalidExternalSignal):
        ExternalSignal.from_raw_payload(payload)


def test_external_signal_with_symbol_mismatch_is_rejected():
    payload = {
        "source_id": "x", "organization_id": "org", "symbol": "AAPL", "signal": "BUY",
        "confidence": 0.5, "rationale": "test",
    }
    with pytest.raises(InvalidExternalSignal):
        ExternalSignal.from_raw_payload(payload, expected_symbol="MSFT")


def test_external_signal_with_malformed_risk_flags_is_rejected():
    payload = {
        "source_id": "x", "organization_id": "org", "symbol": "AAPL", "signal": "BUY",
        "confidence": 0.5, "rationale": "test", "risk_flags": "not-a-list",
    }
    with pytest.raises(InvalidExternalSignal):
        ExternalSignal.from_raw_payload(payload)


# ── 3. Resultat normalise -> meme chemin de gouvernance que le natif ────────


def test_normalized_external_signal_produces_decision_via_same_bridge_as_native():
    """
    Prouve qu'aucune duplication n'existe : le meme KX108GovernanceBridge
    (F5, inchange) produit une Decision a partir d'un signal externe
    normalise exactement comme il le ferait a partir d'un signal natif.
    """
    state = TradingState(symbol="AAPL", prices=[100.0, 101.0], highs=[101.0, 102.0],
                          lows=[99.0, 100.0], volumes=[1000.0, 1100.0])
    native_output = agent_vote_to_agent_output(MarketDataAgent().evaluate(state))

    external_signal = ExternalSignal.from_raw_payload(
        {
            "source_id": "brother_strategy_07", "organization_id": "brother_company",
            "symbol": "AAPL",
            "signal": "BUY", "confidence": 0.9, "rationale": "meme confiance que le natif",
        }
    )
    external_output = normalize_external_signal(external_signal, adapter_id="brother_stack_v1")

    domain_state = TradingDomainState(cycle_id="c-test", observed_at=0.0, mode=Mode.PAPER)
    bridge = KX108GovernanceBridge(StaticKX108Client(response={"verdict": "ACT"}))
    decision_native = bridge.evaluate(_proposal_with(native_output), state=domain_state, decision_id="d-native")
    decision_external = bridge.evaluate(_proposal_with(external_output), state=domain_state, decision_id="d-external")

    # Meme bridge, meme client KX108, meme forme de Decision : aucune
    # branche de code specifique a "external" dans la gouvernance.
    assert decision_native.authority == decision_external.authority == Authority.ACT
    assert type(decision_native) is type(decision_external)


# ── 4. Aucun import execution.binder / market.adapters.alpaca dans external/ ──


def test_external_package_has_no_binder_or_broker_import():
    """
    Ne regarde QUE les lignes d'import reelles (`import X` / `from X import`),
    pas les mentions en docstring/commentaire qui EXPLIQUENT la regle (ex:
    "n'importe jamais execution.binder" dans une docstring contient la
    sous-chaine interdite sans etre un import).
    """
    root = pathlib.Path("external")
    forbidden = ("execution.binder", "market.adapters.alpaca")
    offenders = []
    for path in root.rglob("*.py"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if not (stripped.startswith("import ") or stripped.startswith("from ")):
                continue
            for token in forbidden:
                if token in stripped:
                    offenders.append((path, lineno, stripped))
    assert offenders == [], f"import interdit trouve dans external/: {offenders}"


# ── 5. Le normalizer ne modifie jamais governance/bridge/ ──────────────────


def test_normalizer_and_adapters_never_import_governance_bridge():
    """
    Adapter != Governance : ce module ne doit avoir aucun moyen de modifier
    le comportement du Governance Bridge — seulement de lui SOUMETTRE un
    Canonical Contract, exactement comme le chemin natif (qui n'importe pas
    non plus governance.bridge dans native/agents/adapter.py).
    """
    for path in (
        pathlib.Path("external/normalization/normalizer.py"),
        pathlib.Path("external/adapters/base_adapter.py"),
        pathlib.Path("external/contracts/external_signal.py"),
    ):
        text = path.read_text(encoding="utf-8")
        assert "governance.bridge" not in text, f"{path} ne doit pas importer governance.bridge"


# ── 6. unknowns/contradictions/risk_flags survivent la normalisation ───────


def test_unknowns_contradictions_risk_flags_survive_normalization():
    signal = ExternalSignal.from_raw_payload(
        {
            "source_id": "ext-1", "organization_id": "org", "symbol": "AAPL",
            "signal": "SELL", "confidence": 0.4, "observed_at": time.time(),
            "rationale": "test", "unknowns": ("no_orderbook",), "contradictions": ("trend_conflict",),
            "risk_flags": ("thin_liquidity",), "evidence_refs": ("ref-1",),
        }
    )
    output = normalize_external_signal(signal, adapter_id="adapter-x")

    # F15 : la staleness FRESH/UNKNOWN et l'absence de calibration externe
    # sont ajoutees comme unknowns supplementaires — le unknown metier
    # original doit rester present tel quel parmi eux, jamais remplace.
    assert "no_orderbook" in output.unknowns
    assert output.contradictions == ("trend_conflict",)
    assert output.risk_flags == ("thin_liquidity",)
    assert output.evidence_refs == ("ref-1",)


# ── 7. organization_id + adapter_id + source_id conserves bout-en-bout ─────


def test_organization_adapter_and_source_id_all_survive_full_pipeline(tmp_path):
    from domain.market import MarketSnapshot
    from domain.orders import ExecutionResult
    from domain.portfolio import AccountState, PortfolioState
    from domain.proposal import StrategyCandidate
    from domain.types import AssetClass, DataQuality, Mode, OrderStatus, Provenance
    from execution.binder.engine import CycleEngine
    from execution.binder.planner import ExecutionPlanner
    from proof.receipts.receipt_store import ReceiptStore
    from tests.test_support.kx108_fixtures import FixtureKX108Client

    class FakeMarketData:
        def snapshot(self, symbol):
            return self.snapshots([symbol])[symbol]

        def snapshots(self, symbols):
            return {
                s: MarketSnapshot(symbol=s, asset_class=AssetClass.EQUITY, last_price=100.0,
                                   provenance=Provenance(source="fake", fetched_at=0.0,
                                                          quality=DataQuality.LIVE, mode=Mode.PAPER),
                                   tradable=True, market_open=True)
                for s in symbols
            }

        def history(self, symbol, limit=200):
            return ()

        def context(self):
            return None

    class FakeBroker:
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

        def submit(self, plan):
            return ExecutionResult(plan=plan, submitted=True, status=OrderStatus.ACCEPTED,
                                    broker_order_id="fake-1", mode=Mode.PAPER.value)

        def close_position(self, plan):
            raise NotImplementedError

    class FakeAggregation:
        def aggregate(self, outputs):
            return Consensus(side="BUY", confidence=0.9)

    class FakeStrategy:
        def build(self, symbol, snapshot, consensus, portfolio, opportunities=()):
            return (StrategyCandidate(symbol=symbol, action=ActionKind.BUY, rationale="F8 fixture",
                                       confidence=0.9, order_type=OrderType.MARKET,
                                       strategy_id="fixture-strategy"),)

    class FakeSizing:
        def size(self, candidate, snapshot, portfolio):
            return SizingDecision(quantity=1.0, requested_quantity=1.0)

    adapter = ExampleBrotherStackAdapter()
    analysis = ExternalStackAnalysisAdapter(adapter)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        kx108 = FixtureKX108Client(verdict="ACT")
    bridge = KX108GovernanceBridge(kx108)

    store = ReceiptStore(tmp_path / "receipts.jsonl")
    engine = CycleEngine(
        market_data=FakeMarketData(), broker=FakeBroker(), analysis=analysis,
        aggregation=FakeAggregation(), authority=bridge, symbols=["AAPL"], mode=Mode.PAPER,
        strategy=FakeStrategy(), sizing=FakeSizing(), planner=ExecutionPlanner(), proof=store,
    )
    outcome = engine.run_cycle()

    persisted = outcome.receipt.as_dict()["decision"]["proposal"]["agent_outputs"][0]["source_provenance"]
    assert persisted["source_id"] == "brother_strategy_07"
    assert persisted["adapter_id"] == "brother_stack_v1"
    assert persisted["organization_id"] == "brother_company"
