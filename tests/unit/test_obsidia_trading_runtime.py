"""
P1-D — ObsidiaTradingRuntime : facade produit stable.

Ces tests couvrent la config, l'assemblage (`build`), le sizing, l'etat
KX108 observe/configure, la delegation stricte de `run_cycle`, la preuve et
le replay sans effet de bord, ainsi que les frontieres architecturales
(aucun import UI, aucune dependance a un client de test KX108).

`ObsidiaTradingRuntime.build()` assemble un vrai `AlpacaHTTPClient`/
`AlpacaBroker`/`AlpacaMarketDataProvider` (construction pure, aucun appel
reseau a la construction) : les tests BUILD utilisent des identifiants
Alpaca FACTICES via `monkeypatch.setenv` (jamais les vraies cles `.env`),
et n'appellent jamais `run_cycle()` sur un runtime construit via `build()`
(qui declencherait un vrai appel reseau). Les tests de cycle/KX108-status
construisent `ObsidiaTradingRuntime` directement avec un `CycleEngine` factice.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from domain.calibration import CalibrationPack, DatasetDescriptor
from domain.receipt import Decision
from domain.state import TradingDomainState
from domain.types import Authority, Mode
from execution.binder.engine import CycleOutcome
from execution.binder.proof_policy import ProofPolicy
from governance.bridge.kx108_client import RealKX108Client
from native.agents.aggregation import NativeRosterAggregation
from native.agents.calibrated_agents import CalibrationAwareVolatilityAgent
from native.sizing.native_reference_sizing import NativeReferenceSizing
from native.sizing.sizing_policy import SizingPolicy
from native.strategy.native_consensus_strategy import NativeReferenceStrategy
from proof.receipts.receipt_store import ReceiptStore
from proof.receipts.replay import AuditReplayResult

from runtime.config import InvalidRuntimeConfig, RuntimeConfig
from runtime.obsidia_trading_runtime import ObsidiaTradingRuntime, ReplayUnavailable
from runtime.status import (
    AgentsStatus,
    CalibrationStatus,
    KX108Status,
    MarketStatus,
    ModeStatus,
    ProofStatus,
    ReceiptStoreStatus,
    ReplayStatus,
    SizingStatus,
    StrategyStatus,
)

RUNTIME_SOURCE_FILES = tuple(Path("runtime").glob("*.py"))


def _set_fake_alpaca_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Identifiants Alpaca FACTICES pour la construction (jamais un appel reseau)."""
    monkeypatch.setenv("ALPACA_MODE", "paper")
    monkeypatch.setenv("ALPACA_API_KEY", "test-fake-key-not-real")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-fake-secret-not-real")


def _minimal_config(tmp_path: Path, **overrides) -> RuntimeConfig:
    defaults = dict(
        symbols=("AAPL",),
        order_ledger_path=str(tmp_path / "orders.jsonl"),
    )
    defaults.update(overrides)
    return RuntimeConfig(**defaults)


def _fake_calibration_pack() -> CalibrationPack:
    dataset = DatasetDescriptor(
        source="test_fixture",
        symbol="AAPL",
        timeframe="1D",
        start=None,
        end=None,
        observation_count=1,
        retrieved_at="2026-01-01T00:00:00+00:00",
    )
    return CalibrationPack.build(dataset=dataset, models=(), method="test_v1")


class _StubEngine:
    """Double minimal de CycleEngine : compte les appels, retourne un outcome fixe."""

    def __init__(self, outcome: CycleOutcome) -> None:
        self._outcome = outcome
        self.call_count = 0

    def run_cycle(self) -> CycleOutcome:
        self.call_count += 1
        return self._outcome


def _runtime_with_stub_engine(
    outcome: CycleOutcome,
    *,
    config: RuntimeConfig,
    receipt_store=None,
    replay_engine=None,
) -> tuple[ObsidiaTradingRuntime, _StubEngine]:
    engine = _StubEngine(outcome)
    runtime = ObsidiaTradingRuntime(
        engine=engine,  # type: ignore[arg-type]
        config=config,
        receipt_store=receipt_store,
        replay_engine=replay_engine,
    )
    return runtime, engine


def _outcome_with_decision(metrics: dict) -> CycleOutcome:
    state = TradingDomainState(cycle_id="c1", observed_at=0.0, mode=Mode.PAPER)
    decision = Decision(
        decision_id="d1",
        authority=Authority.HOLD,
        reason="test",
        proposal=None,  # type: ignore[arg-type]
        metrics=metrics,
    )
    return CycleOutcome(cycle_id="c1", state=state, decision=decision)


# ═══════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════


def test_config_is_deterministic(tmp_path):
    a = _minimal_config(tmp_path)
    b = _minimal_config(tmp_path)
    assert a == b


def test_config_has_no_mode_field(tmp_path):
    """Reference Runtime V1 est structurellement PAPER : pas de champ mode exposable en LIVE."""
    config = _minimal_config(tmp_path)
    assert not hasattr(config, "mode")


def test_config_requires_symbols(tmp_path):
    with pytest.raises(InvalidRuntimeConfig):
        _minimal_config(tmp_path, symbols=())


def test_config_requires_order_ledger_path(tmp_path):
    with pytest.raises(InvalidRuntimeConfig):
        _minimal_config(tmp_path, order_ledger_path="")


def test_config_sizing_policy_optional(tmp_path):
    config = _minimal_config(tmp_path)
    assert config.sizing_policy is None


def test_config_calibration_pack_optional(tmp_path):
    config = _minimal_config(tmp_path)
    assert config.calibration_pack is None


# ═══════════════════════════════════════════════════════════════════════════
# BUILD
# ═══════════════════════════════════════════════════════════════════════════


def test_build_uses_real_kx108_client(tmp_path, monkeypatch):
    _set_fake_alpaca_env(monkeypatch)
    runtime = ObsidiaTradingRuntime.build(_minimal_config(tmp_path))
    assert isinstance(runtime._engine.authority.client, RealKX108Client)


def test_build_proof_policy_required(tmp_path, monkeypatch):
    _set_fake_alpaca_env(monkeypatch)
    runtime = ObsidiaTradingRuntime.build(_minimal_config(tmp_path))
    assert runtime._engine.proof_policy is ProofPolicy.REQUIRED


def test_build_wires_native_reference_strategy(tmp_path, monkeypatch):
    _set_fake_alpaca_env(monkeypatch)
    runtime = ObsidiaTradingRuntime.build(_minimal_config(tmp_path))
    assert isinstance(runtime._engine.strategy, NativeReferenceStrategy)


def test_build_wires_native_reference_sizing(tmp_path, monkeypatch):
    _set_fake_alpaca_env(monkeypatch)
    policy = SizingPolicy(target_notional=100.0, quantity_increment=1.0)
    runtime = ObsidiaTradingRuntime.build(_minimal_config(tmp_path, sizing_policy=policy))
    assert isinstance(runtime._engine.sizing, NativeReferenceSizing)
    assert runtime._engine.sizing._policy is policy


def test_build_wires_native_roster_aggregation(tmp_path, monkeypatch):
    _set_fake_alpaca_env(monkeypatch)
    runtime = ObsidiaTradingRuntime.build(_minimal_config(tmp_path))
    assert isinstance(runtime._engine.aggregation, NativeRosterAggregation)


def test_build_uses_standard_roster_without_calibration_pack(tmp_path, monkeypatch):
    _set_fake_alpaca_env(monkeypatch)
    runtime = ObsidiaTradingRuntime.build(_minimal_config(tmp_path))
    agents = runtime._engine.analysis._agents
    assert len(agents) == 17
    assert not any(isinstance(a, CalibrationAwareVolatilityAgent) for a in agents)


def test_build_uses_calibrated_roster_when_pack_provided(tmp_path, monkeypatch):
    _set_fake_alpaca_env(monkeypatch)
    pack = _fake_calibration_pack()
    runtime = ObsidiaTradingRuntime.build(_minimal_config(tmp_path, calibration_pack=pack))
    agents = runtime._engine.analysis._agents
    assert any(isinstance(a, CalibrationAwareVolatilityAgent) for a in agents)


def test_build_invalid_config_fails_at_construction(tmp_path, monkeypatch):
    _set_fake_alpaca_env(monkeypatch)
    with pytest.raises(InvalidRuntimeConfig):
        ObsidiaTradingRuntime.build(_minimal_config(tmp_path, symbols=()))


# ═══════════════════════════════════════════════════════════════════════════
# SIZING
# ═══════════════════════════════════════════════════════════════════════════


def test_status_sizing_not_configured_without_policy(tmp_path, monkeypatch):
    _set_fake_alpaca_env(monkeypatch)
    runtime = ObsidiaTradingRuntime.build(_minimal_config(tmp_path))
    assert runtime.status().sizing is SizingStatus.NOT_CONFIGURED


def test_status_sizing_configured_with_explicit_policy(tmp_path, monkeypatch):
    _set_fake_alpaca_env(monkeypatch)
    policy = SizingPolicy(target_notional=100.0, quantity_increment=1.0)
    runtime = ObsidiaTradingRuntime.build(_minimal_config(tmp_path, sizing_policy=policy))
    assert runtime.status().sizing is SizingStatus.CONFIGURED


def test_sizing_remains_fail_closed_without_policy():
    """Rappel P1-C : NativeReferenceSizing(None) rejette toujours, la facade ne change rien."""
    decision = NativeReferenceSizing(None).size(candidate=None, snapshot=None, portfolio=None)  # type: ignore[arg-type]
    assert decision.status == "REJECTED"
    assert decision.rationale == "SIZING_POLICY_NOT_CONFIGURED"


# ═══════════════════════════════════════════════════════════════════════════
# KX108 STATUS
# ═══════════════════════════════════════════════════════════════════════════


def test_status_before_any_cycle_is_real_client_configured(tmp_path):
    outcome = _outcome_with_decision({})
    runtime, _ = _runtime_with_stub_engine(outcome, config=_minimal_config(tmp_path))
    assert runtime.status().kx108 is KX108Status.REAL_CLIENT_CONFIGURED


def test_status_promotes_to_real_observed_on_real_evidence(tmp_path):
    outcome = _outcome_with_decision(
        {"kx108_response": {"source": "KX108_REAL", "verdict": "HOLD"}}
    )
    runtime, _ = _runtime_with_stub_engine(outcome, config=_minimal_config(tmp_path))
    runtime.run_cycle()
    assert runtime.status().kx108 is KX108Status.REAL_OBSERVED


def test_status_unavailable_on_fail_closed_evidence(tmp_path):
    outcome = _outcome_with_decision({"fail_closed": True})
    runtime, _ = _runtime_with_stub_engine(outcome, config=_minimal_config(tmp_path))
    runtime.run_cycle()
    assert runtime.status().kx108 is KX108Status.UNAVAILABLE


def test_status_unchanged_when_kernel_never_invoked(tmp_path):
    """Cycle d'abstention (decision=None, aucun appel a l'autorite) : pas d'evidence, pas de changement."""
    state = TradingDomainState(cycle_id="c1", observed_at=0.0, mode=Mode.PAPER)
    outcome = CycleOutcome(cycle_id="c1", state=state, decision=None)
    runtime, _ = _runtime_with_stub_engine(outcome, config=_minimal_config(tmp_path))
    runtime.run_cycle()
    assert runtime.status().kx108 is KX108Status.REAL_CLIENT_CONFIGURED


def test_status_market_observed_after_cycle_with_market_data(tmp_path):
    from domain.market import MarketSnapshot
    from domain.types import AssetClass, DataQuality, Provenance

    snapshot = MarketSnapshot(
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        last_price=100.0,
        provenance=Provenance(source="test", fetched_at=0.0, quality=DataQuality.LIVE, mode=Mode.PAPER),
    )
    state = TradingDomainState(
        cycle_id="c1", observed_at=0.0, mode=Mode.PAPER, market={"AAPL": snapshot}
    )
    outcome = CycleOutcome(cycle_id="c1", state=state, decision=None)
    runtime, _ = _runtime_with_stub_engine(outcome, config=_minimal_config(tmp_path))
    runtime.run_cycle()
    assert runtime.status().market is MarketStatus.OBSERVED


def test_status_market_degraded_reflects_degraded_reasons(tmp_path):
    state = TradingDomainState(
        cycle_id="c1", observed_at=0.0, mode=Mode.PAPER,
        degraded_reasons=("donnees de marche indisponibles: x",),
    )
    outcome = CycleOutcome(cycle_id="c1", state=state, decision=None)
    runtime, _ = _runtime_with_stub_engine(outcome, config=_minimal_config(tmp_path))
    runtime.run_cycle()
    assert runtime.status().market is MarketStatus.DEGRADED


def test_status_market_not_observed_before_any_cycle(tmp_path):
    outcome = _outcome_with_decision({})
    runtime, _ = _runtime_with_stub_engine(outcome, config=_minimal_config(tmp_path))
    assert runtime.status().market is MarketStatus.NOT_OBSERVED


# ═══════════════════════════════════════════════════════════════════════════
# CYCLE
# ═══════════════════════════════════════════════════════════════════════════


def test_run_cycle_delegates_exactly_once(tmp_path):
    outcome = _outcome_with_decision({})
    runtime, engine = _runtime_with_stub_engine(outcome, config=_minimal_config(tmp_path))
    result = runtime.run_cycle()
    assert engine.call_count == 1
    assert result is outcome


def test_facade_does_not_recompute_decision(tmp_path):
    outcome = _outcome_with_decision({"kx108_response": {"source": "KX108_REAL", "verdict": "HOLD"}})
    runtime, _ = _runtime_with_stub_engine(outcome, config=_minimal_config(tmp_path))
    result = runtime.run_cycle()
    assert result.decision is outcome.decision
    assert result.decision.authority is Authority.HOLD


def test_facade_produces_no_authority_itself():
    """La facade n'importe/instancie jamais Authority pour produire une decision."""
    source = Path("runtime/obsidia_trading_runtime.py").read_text(encoding="utf-8")
    assert "import Authority" not in source
    assert re.search(r"\bAuthority\s*\(", source) is None
    assert re.search(r"\bAuthority\.(ACT|HOLD|BLOCK)\b", source) is None


# ═══════════════════════════════════════════════════════════════════════════
# PROOF
# ═══════════════════════════════════════════════════════════════════════════


def test_build_always_uses_proof_required(tmp_path, monkeypatch):
    _set_fake_alpaca_env(monkeypatch)
    runtime = ObsidiaTradingRuntime.build(_minimal_config(tmp_path))
    assert runtime.status().proof is ProofStatus.REQUIRED


def test_receipt_store_reused_when_configured(tmp_path, monkeypatch):
    _set_fake_alpaca_env(monkeypatch)
    receipt_path = str(tmp_path / "receipts.jsonl")
    runtime = ObsidiaTradingRuntime.build(_minimal_config(tmp_path, receipt_store_path=receipt_path))
    assert isinstance(runtime._receipt_store, ReceiptStore)
    assert runtime._engine.proof is runtime._receipt_store
    assert runtime.status().receipt_store is ReceiptStoreStatus.CONFIGURED


def test_receipt_store_unavailable_without_path(tmp_path, monkeypatch):
    _set_fake_alpaca_env(monkeypatch)
    runtime = ObsidiaTradingRuntime.build(_minimal_config(tmp_path))
    assert runtime._receipt_store is None
    assert runtime.status().receipt_store is ReceiptStoreStatus.UNAVAILABLE


def test_get_receipt_and_history_honest_without_store(tmp_path):
    outcome = _outcome_with_decision({})
    runtime, _ = _runtime_with_stub_engine(outcome, config=_minimal_config(tmp_path))
    assert runtime.get_receipt("c1") is None
    assert runtime.history() == ()


def test_get_receipt_and_history_delegate_to_store(tmp_path):
    store = ReceiptStore(str(tmp_path / "receipts.jsonl"))
    outcome = _outcome_with_decision({})
    runtime, _ = _runtime_with_stub_engine(
        outcome, config=_minimal_config(tmp_path), receipt_store=store
    )
    assert runtime.get_receipt("does-not-exist") is None
    assert runtime.history() == ()


# ═══════════════════════════════════════════════════════════════════════════
# REPLAY
# ═══════════════════════════════════════════════════════════════════════════


def test_replay_unavailable_without_receipt_store(tmp_path):
    outcome = _outcome_with_decision({})
    runtime, _ = _runtime_with_stub_engine(outcome, config=_minimal_config(tmp_path))
    with pytest.raises(ReplayUnavailable):
        runtime.replay("c1")


def test_replay_delegates_to_replay_engine_side_effect_free(tmp_path):
    store = ReceiptStore(str(tmp_path / "receipts.jsonl"))
    from proof.receipts.replay import ReplayEngine

    replay_engine = ReplayEngine(store)
    outcome = _outcome_with_decision({})
    runtime, _ = _runtime_with_stub_engine(
        outcome, config=_minimal_config(tmp_path), receipt_store=store, replay_engine=replay_engine
    )
    result = runtime.replay("does-not-exist")
    assert isinstance(result, AuditReplayResult)
    assert result.found is False


def test_status_replay_available_with_store(tmp_path, monkeypatch):
    _set_fake_alpaca_env(monkeypatch)
    receipt_path = str(tmp_path / "receipts.jsonl")
    runtime = ObsidiaTradingRuntime.build(_minimal_config(tmp_path, receipt_store_path=receipt_path))
    assert runtime.status().replay is ReplayStatus.AVAILABLE


def test_status_replay_unavailable_without_store(tmp_path, monkeypatch):
    _set_fake_alpaca_env(monkeypatch)
    runtime = ObsidiaTradingRuntime.build(_minimal_config(tmp_path))
    assert runtime.status().replay is ReplayStatus.UNAVAILABLE


# ═══════════════════════════════════════════════════════════════════════════
# BOUNDARIES
# ═══════════════════════════════════════════════════════════════════════════


def test_runtime_has_no_ui_imports():
    forbidden = re.compile(r"^\s*(from|import)\s+(apps|streamlit)\b", re.MULTILINE)
    for path in RUNTIME_SOURCE_FILES:
        text = path.read_text(encoding="utf-8")
        assert not forbidden.search(text), f"{path} importe l'UI, ce qui est interdit pour runtime/"


def test_runtime_has_no_fixture_kx108_dependency():
    """
    Aucun IMPORT ni INSTANCIATION reelle d'un client KX108 de test dans
    runtime/ (une simple mention en prose de docstring, ex: "jamais
    FixtureKX108Client", n'est pas une violation).
    """
    forbidden = re.compile(
        r"(?:from\s+\S+\s+import\s+.*\b(FixtureKX108Client|StaticKX108Client|StaticKX108TestClient)\b"
        r"|\b(FixtureKX108Client|StaticKX108Client|StaticKX108TestClient)\s*\()"
    )
    for path in RUNTIME_SOURCE_FILES:
        text = path.read_text(encoding="utf-8")
        assert not forbidden.search(text), f"{path} importe/instancie un client KX108 de test"


def test_runtime_does_not_duplicate_strategy_sizing_semantics():
    """La facade ne redefinit ni Consensus.side -> action, ni de formule de quantite."""
    text = Path("runtime/obsidia_trading_runtime.py").read_text(encoding="utf-8")
    assert "consensus.side" not in text
    assert "ROUND_DOWN" not in text
    assert "quantity_increment" not in text


def test_runtime_does_not_import_binder_planner_or_broker_directly():
    text = Path("runtime/obsidia_trading_runtime.py").read_text(encoding="utf-8")
    assert "AlpacaBroker" not in text
    assert "ExecutionPlanner" not in text
    assert "JsonlOrderLedger" not in text


def test_agents_status_reflects_calibration_choice(tmp_path):
    outcome = _outcome_with_decision({})
    runtime, _ = _runtime_with_stub_engine(outcome, config=_minimal_config(tmp_path))
    assert runtime.status().agents is AgentsStatus.NATIVE_17
    assert runtime.status().calibration is CalibrationStatus.NOT_CONFIGURED

    pack = _fake_calibration_pack()
    runtime_calibrated, _ = _runtime_with_stub_engine(
        outcome, config=_minimal_config(tmp_path, calibration_pack=pack)
    )
    assert runtime_calibrated.status().agents is AgentsStatus.NATIVE_17_CALIBRATED
    assert runtime_calibrated.status().calibration is CalibrationStatus.CONFIGURED


def test_status_mode_is_always_paper(tmp_path):
    outcome = _outcome_with_decision({})
    runtime, _ = _runtime_with_stub_engine(outcome, config=_minimal_config(tmp_path))
    assert runtime.status().mode is ModeStatus.PAPER


def test_status_strategy_is_always_native_reference(tmp_path):
    outcome = _outcome_with_decision({})
    runtime, _ = _runtime_with_stub_engine(outcome, config=_minimal_config(tmp_path))
    assert runtime.status().strategy is StrategyStatus.NATIVE_REFERENCE
