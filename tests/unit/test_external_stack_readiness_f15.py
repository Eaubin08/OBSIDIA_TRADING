"""
F15 — External Stack Integration Readiness.

Complete les tests F8 (tests/unit/test_external_adapter.py) avec les cas
specifiques a F15 : staleness, calibration externe (absente/presente),
frontieres d'autorite, non-regression Native, PAPER/PROOF_REQUIRED intacts,
replay sans effet de bord pour un cycle External.

Ceci ne pretend jamais integrer une vraie stack externe (aucune n'existe
encore) — uniquement le contrat generique et sa robustesse.
"""
from __future__ import annotations

import pathlib
import time
import warnings

import pytest

from external.contracts.external_signal import (
    ExternalCalibrationMetadata,
    ExternalSignal,
    NO_EXTERNAL_CALIBRATION_INFORMATION,
)
from external.normalization.normalizer import normalize_external_signal


def _payload(**overrides):
    base = dict(
        source_id="brother_strategy_07", organization_id="brother_company",
        symbol="AAPL", signal="BUY", confidence=0.6, rationale="f15 test",
    )
    base.update(overrides)
    return base


# ── Staleness du signal lui-meme ────────────────────────────────────────


def test_signal_without_observed_at_is_staleness_unknown_not_fresh():
    signal = ExternalSignal.from_raw_payload(_payload())
    assert signal.observed_at is None
    assert signal.staleness_status() == "UNKNOWN"


def test_signal_with_recent_observed_at_is_fresh():
    signal = ExternalSignal.from_raw_payload(_payload(observed_at=time.time()))
    assert signal.staleness_status() == "FRESH"


def test_signal_with_old_observed_at_is_stale():
    old = time.time() - 10_000.0
    signal = ExternalSignal.from_raw_payload(_payload(observed_at=old))
    assert signal.staleness_status(max_age_seconds=900.0) == "STALE"


def test_staleness_never_silently_upgraded_to_fresh_in_normalization():
    """
    Un signal dont la fraicheur est UNKNOWN ou STALE doit se retrouver comme
    unknown explicite apres normalisation — jamais disparaitre en "FRESH"
    par defaut.
    """
    signal = ExternalSignal.from_raw_payload(_payload())  # observed_at absent -> UNKNOWN
    output = normalize_external_signal(signal, adapter_id="a1")
    assert any(u.startswith("external_signal_staleness=UNKNOWN") for u in output.unknowns)


# ── Calibration externe absente / presente ──────────────────────────────


def test_calibration_absent_yields_explicit_sentinel_not_fabricated_values():
    signal = ExternalSignal.from_raw_payload(_payload())
    assert signal.calibration.external_calibration_id == NO_EXTERNAL_CALIBRATION_INFORMATION
    assert not signal.calibration.is_present
    assert signal.calibration.staleness_status() == "UNKNOWN"


def test_calibration_absent_surfaces_as_unknown_in_canonical_output():
    signal = ExternalSignal.from_raw_payload(_payload())
    output = normalize_external_signal(signal, adapter_id="a1")
    assert any(
        u == f"external_calibration={NO_EXTERNAL_CALIBRATION_INFORMATION}"
        for u in output.unknowns
    )


def test_calibration_present_is_parsed_and_traceable_in_evidence():
    now = time.time()
    signal = ExternalSignal.from_raw_payload(
        _payload(
            calibration={
                "external_calibration_id": "brother-calib-001",
                "dataset_reference": "brother_internal_dataset_v3",
                "calibration_version": "v3",
                "created_at": now - 60,
                "valid_until": now + 3600,
                "evidence_refs": ["brother:evidence:1"],
            }
        )
    )
    assert signal.calibration.is_present
    assert signal.calibration.staleness_status(now=now) == "FRESH"

    output = normalize_external_signal(signal, adapter_id="a1")
    assert "brother:evidence:1" in output.evidence_refs
    assert output.inputs_digest["external_calibration_id"] == "brother-calib-001"
    # Le CalibrationPack Native n'est jamais mentionne ni requis ici.
    assert not any("calibration.v1" in str(v) for v in output.inputs_digest.values())


def test_expired_external_calibration_is_surfaced_as_stale_unknown():
    now = time.time()
    signal = ExternalSignal.from_raw_payload(
        _payload(
            calibration={
                "external_calibration_id": "brother-calib-002",
                "valid_until": now - 3600,
            }
        )
    )
    assert signal.calibration.staleness_status(now=now) == "STALE"
    output = normalize_external_signal(signal, adapter_id="a1")
    assert any(u.startswith("external_calibration_staleness=STALE") for u in output.unknowns)


# ── Frontieres d'autorite (complement des tests F8 deja existants) ──────


def test_external_package_never_imports_kx108_client_or_authority_types_directly():
    """
    Adapter != KX108 authority : aucun fichier sous external/ ne doit
    importer directement le client KX108 ou construire une Authority/
    Decision lui-meme — seul le Governance Bridge (F5) le fait.
    """
    root = pathlib.Path("external")
    forbidden = ("governance.bridge.kx108_client", "domain.types.Authority")
    offenders = []
    for path in root.rglob("*.py"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if not (stripped.startswith("import ") or stripped.startswith("from ")):
                continue
            for token in forbidden:
                if token in stripped:
                    offenders.append((str(path), lineno, stripped))
    assert offenders == [], f"import interdit trouve dans external/: {offenders}"


# ── PAPER only / PROOF_REQUIRED / replay sans effet de bord (chemin External) ──


def _build_external_cycle_engine(tmp_path):
    from domain.market import MarketSnapshot
    from domain.orders import ExecutionResult
    from domain.portfolio import AccountState, PortfolioState
    from domain.proposal import Consensus, SizingDecision, StrategyCandidate
    from domain.types import ActionKind, AssetClass, DataQuality, Mode, OrderStatus, OrderType, Provenance
    from execution.binder.engine import CycleEngine
    from execution.binder.planner import ExecutionPlanner
    from external.adapters.base_adapter import ExternalStackAnalysisAdapter
    from external.examples.brother_stack.example_adapter import ExampleBrotherStackAdapter
    from governance.bridge.governance_bridge import KX108GovernanceBridge
    from proof.receipts.receipt_store import ReceiptStore
    from tests.test_support.kx108_fixtures import FixtureKX108Client

    class FakeMarketData:
        def snapshot(self, symbol):
            return self.snapshots([symbol])[symbol]

        def snapshots(self, symbols):
            return {
                s: MarketSnapshot(
                    symbol=s, asset_class=AssetClass.EQUITY, last_price=100.0,
                    provenance=Provenance(source="fake", fetched_at=0.0,
                                           quality=DataQuality.LIVE, mode=Mode.PAPER),
                    tradable=True, market_open=True,
                )
                for s in symbols
            }

        def history(self, symbol, limit=200):
            return ()

        def context(self):
            return None

    class FakeBroker:
        def __init__(self):
            self.submit_calls = 0

        def account(self):
            return AccountState(
                equity=100_000.0, cash=100_000.0, buying_power=100_000.0,
                provenance=Provenance(source="fake", fetched_at=0.0,
                                       quality=DataQuality.LIVE, mode=Mode.PAPER),
                trading_blocked=False,
            )

        def positions(self):
            return ()

        def open_orders(self):
            return ()

        def portfolio(self):
            return PortfolioState(account=self.account())

        def submit(self, plan):
            self.submit_calls += 1
            return ExecutionResult(plan=plan, submitted=True, status=OrderStatus.ACCEPTED,
                                    broker_order_id="fake-ext-1", mode=Mode.PAPER.value)

        def close_position(self, plan):
            raise NotImplementedError

    class FakeAggregation:
        def aggregate(self, outputs):
            return Consensus(side="BUY", confidence=0.9)

    class FakeStrategy:
        def build(self, symbol, snapshot, consensus, portfolio, opportunities=()):
            return (StrategyCandidate(symbol=symbol, action=ActionKind.BUY, rationale="F15 fixture",
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
    broker = FakeBroker()
    engine = CycleEngine(
        market_data=FakeMarketData(), broker=broker, analysis=analysis,
        aggregation=FakeAggregation(), authority=bridge, symbols=["AAPL"], mode=Mode.PAPER,
        strategy=FakeStrategy(), sizing=FakeSizing(), planner=ExecutionPlanner(), proof=store,
    )
    return engine, broker, store


def test_external_path_paper_only_binder_not_bypassed(tmp_path):
    """
    KX108=ACT via le chemin External ne suffit pas a executer : le Binder
    (ExecutionPlanner + garde interne de CycleEngine) reste seul juge, et
    aucune execution live n'est possible (Mode.PAPER impose explicitement).
    """
    engine, broker, _store = _build_external_cycle_engine(tmp_path)
    outcome = engine.run_cycle()
    assert outcome.decision.authority.value == "ACT"
    assert broker.submit_calls == 1
    assert outcome.execution is not None
    assert outcome.execution.mode == "PAPER"


def test_external_cycle_replay_audit_has_zero_broker_side_effect(tmp_path):
    """
    Replay != Execution, aussi vrai pour un cycle External : rejouer un
    receipt externe stocke ne doit jamais rappeler le broker.
    """
    from proof.receipts.replay import ReplayEngine

    engine, broker, store = _build_external_cycle_engine(tmp_path)
    outcome = engine.run_cycle()
    calls_before_replay = broker.submit_calls

    replay_engine = ReplayEngine(store)
    result = replay_engine.replay_audit(outcome.receipt.cycle_id)

    assert result.found is True
    assert broker.submit_calls == calls_before_replay  # aucun nouvel appel


def test_external_signal_survives_receipt_persistence_and_reload(tmp_path):
    """
    Provenance calibration_id (F15) et external_calibration_id retrouvables
    depuis le receipt RECHARGE depuis le store, pas seulement en memoire.
    """
    engine, _broker, store = _build_external_cycle_engine(tmp_path)
    outcome = engine.run_cycle()

    stored = store.find_by_cycle_id(outcome.receipt.cycle_id)
    assert stored is not None
    agent_output = stored.raw["decision"]["proposal"]["agent_outputs"][0]
    assert agent_output["source_provenance"]["source_system"] == "external"
    assert "external_calibration_id" in agent_output["inputs"]
