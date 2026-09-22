"""
F13.1 — tests unitaires (aucun reseau) de la consommation de calibration.

Verifie l'isolation vis-a-vis de governance/execution.binder, le refus
explicite (jamais silencieux) des cas symbol mismatch/stale/absent/
non-calibre, le determinisme, et l'equivalence stricte agent calibre sans
pack == agent vanilla.
"""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from domain.calibration import CalibrationPack, DatasetDescriptor, ModelCalibration, ModelCalibrationStatus
from domain.calibration_consumption import (
    CompatibilityStatus,
    build_full_real_calibration_pack,
    calibrated_daily_volatility_fallback,
    check_compatibility,
    evidence_refs_for_pack,
    garch_calibration_note,
    markov_calibration_note,
)
from native.agents.calibrated_agents import (
    CalibrationAwareRegimeShiftAgent,
    CalibrationAwareVolatilityAgent,
    build_calibrated_trading_agents,
)
from native.agents.contracts import TradingState
from native.agents.domains.trading_agents import RegimeShiftAgent, VolatilityAgent


def _fake_real_dataset(symbol: str = "AAPL", n: int = 300) -> DatasetDescriptor:
    return DatasetDescriptor(
        source="alpaca_market_data_api", symbol=symbol, timeframe="1Day",
        start="2026-01-01", end="2026-06-01", observation_count=n,
        retrieved_at=datetime.now(timezone.utc).isoformat(), quality_flags=(),
    )


def _synthetic_returns(n: int, seed: int = 1) -> list:
    # Suite deterministe (pas numpy.random pour eviter toute dependance a
    # un etat global) — sert uniquement a exercer les estimateurs sur un
    # volume suffisant, jamais presentee comme une donnee reelle.
    out, x = [], seed
    for _ in range(n):
        x = (1103515245 * x + 12345) % (2**31)
        out.append(((x / (2**31)) - 0.5) * 0.02)
    return out


# 20. calibration non retunee selon verdict Kernel + aucune importation
# governance/execution.binder (test structurel AST).
def test_no_governance_or_binder_import_in_calibration_modules():
    for relpath in (
        "domain/calibration_consumption.py",
        "native/agents/calibrated_agents.py",
    ):
        tree = ast.parse(Path(relpath).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = getattr(node, "module", None) or ",".join(n.name for n in node.names)
                assert "governance" not in (mod or ""), f"{relpath} importe {mod}"
                assert "execution.binder" not in (mod or ""), f"{relpath} importe {mod}"


# 4. symbol mismatch -> refus explicite, jamais silencieux
def test_symbol_mismatch_is_refused():
    pack = build_full_real_calibration_pack(_fake_real_dataset("AAPL"), _synthetic_returns(200))
    check = check_compatibility(pack, "MSFT")
    assert check.status is CompatibilityStatus.SYMBOL_MISMATCH
    assert not check.usable


def test_no_pack_is_refused():
    check = check_compatibility(None, "AAPL")
    assert check.status is CompatibilityStatus.NO_PACK
    assert not check.usable


# 5. stale calibration identifiable
def test_stale_pack_is_refused():
    pack = build_full_real_calibration_pack(_fake_real_dataset("AAPL"), _synthetic_returns(200))
    old = pack.created_at
    stale_pack = CalibrationPack(
        calibration_id=pack.calibration_id, schema_version=pack.schema_version,
        dataset=pack.dataset, models=pack.models, method=pack.method,
        created_at=(datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
        status=pack.status,
    )
    check = check_compatibility(stale_pack, "AAPL", max_age_days=1.0)
    assert check.status is CompatibilityStatus.STALE
    assert not check.usable


# 6. missing/non-calibrated calibration -> comportement explicite, jamais invente
def test_not_calibrated_status_is_refused():
    ds_not_real = DatasetDescriptor(
        source="alpaca_market_data_api", symbol="AAPL", timeframe="1Day",
        start=None, end=None, observation_count=0,
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        quality_flags=("NO_CREDENTIALS_CONFIGURED",),
    )
    pack = build_full_real_calibration_pack(ds_not_real, [])
    check = check_compatibility(pack, "AAPL")
    assert check.status is CompatibilityStatus.NOT_CALIBRATED


# 7. meme dataset/returns -> comportement deterministe (meme calibration_id)
def test_build_full_pack_is_deterministic():
    ds = _fake_real_dataset("AAPL")
    returns = _synthetic_returns(200)
    pack1 = build_full_real_calibration_pack(ds, returns)
    pack2 = build_full_real_calibration_pack(ds, returns)
    assert pack1.calibration_id == pack2.calibration_id


def test_different_returns_yield_different_calibration_id():
    ds = _fake_real_dataset("AAPL")
    pack1 = build_full_real_calibration_pack(ds, _synthetic_returns(200, seed=1))
    pack2 = build_full_real_calibration_pack(ds, _synthetic_returns(200, seed=2))
    assert pack1.calibration_id != pack2.calibration_id


# 12. aucun fallback synthetique silencieux
def test_uncalibrated_model_yields_no_synthetic_fallback():
    ds = _fake_real_dataset("AAPL")
    pack = build_full_real_calibration_pack(ds, _synthetic_returns(5))  # insuffisant partout
    assert calibrated_daily_volatility_fallback(pack) is None
    assert "UNCALIBRATED" in (garch_calibration_note(pack) or "")
    assert "UNCALIBRATED" in (markov_calibration_note(pack) or "")


# 8/9. provenance (calibration_id/dataset_digest/schema_version) conservee
def test_evidence_refs_contains_provenance_fields():
    pack = build_full_real_calibration_pack(_fake_real_dataset("AAPL"), _synthetic_returns(200))
    refs = evidence_refs_for_pack(pack)
    joined = " ".join(refs)
    assert pack.calibration_id in joined
    assert pack.dataset.digest() in joined
    assert pack.schema_version in joined


# 10/6bis. Native (VolatilityAgent) sans pack == agent vanilla (aucune substitution silencieuse)
def test_calibrated_volatility_agent_without_pack_matches_vanilla():
    state = TradingState(symbol="AAPL", prices=[100.0 + (i % 7) * 0.3 for i in range(15)])
    vanilla = VolatilityAgent().evaluate(state)
    calibrated = CalibrationAwareVolatilityAgent(None).evaluate(state)
    assert calibrated.proposed_verdict == vanilla.proposed_verdict
    assert calibrated.confidence == vanilla.confidence
    assert calibrated.claim == vanilla.claim
    assert calibrated.unknowns == vanilla.unknowns


def test_calibrated_regimeshift_agent_without_pack_matches_vanilla():
    state = TradingState(symbol="AAPL", prices=[100.0 + (i % 5) * 0.2 for i in range(10)])
    vanilla = RegimeShiftAgent().evaluate(state)
    calibrated = CalibrationAwareRegimeShiftAgent(None).evaluate(state)
    assert calibrated.proposed_verdict == vanilla.proposed_verdict
    assert calibrated.evidence_refs == vanilla.evidence_refs


# symbol mismatch cote agent : refus explicite (unknown), jamais de substitution
def test_calibrated_volatility_agent_symbol_mismatch_is_unknown_not_silent():
    pack = build_full_real_calibration_pack(_fake_real_dataset("AAPL"), _synthetic_returns(200))
    short_prices = [100.0 + (i % 3) * 0.1 for i in range(10)]  # < 61 -> rv60 degrade
    state = TradingState(symbol="MSFT", prices=short_prices)
    vote = CalibrationAwareVolatilityAgent(pack).evaluate(state)
    assert any("SYMBOL_MISMATCH" in u for u in vote.unknowns)


# 1/3. Volatility et GARCH reellement consommes quand le pack est compatible
def test_calibrated_volatility_agent_uses_compatible_pack():
    pack = build_full_real_calibration_pack(_fake_real_dataset("AAPL"), _synthetic_returns(200))
    short_prices = [100.0 + (i % 3) * 0.1 for i in range(10)]  # < 61 -> rv60 degrade -> pack utilise
    state = TradingState(symbol="AAPL", prices=short_prices)
    vote = CalibrationAwareVolatilityAgent(pack).evaluate(state)
    assert pack.calibration_id in vote.claim or any(pack.calibration_id in r for r in vote.evidence_refs)
    assert any("garch_1_1" in r for r in vote.evidence_refs)


# 2. RegimeShift consomme reellement la note Markov calibree (evidence uniquement)
def test_calibrated_regimeshift_agent_attaches_markov_evidence():
    pack = build_full_real_calibration_pack(_fake_real_dataset("AAPL"), _synthetic_returns(200))
    state = TradingState(symbol="AAPL", prices=[100.0 + (i % 4) * 0.15 for i in range(10)])
    vanilla_vote = RegimeShiftAgent().evaluate(state)
    calibrated_vote = CalibrationAwareRegimeShiftAgent(pack).evaluate(state)
    # Le verdict n'est JAMAIS recalcule a partir de la matrice Markov.
    assert calibrated_vote.proposed_verdict == vanilla_vote.proposed_verdict
    assert any("markov_regime_matrix" in r for r in calibrated_vote.evidence_refs)


# 11. build_calibrated_trading_agents ne modifie que Volatility/RegimeShift
def test_build_calibrated_trading_agents_touches_only_two_agents():
    pack = build_full_real_calibration_pack(_fake_real_dataset("AAPL"), _synthetic_returns(200))
    roster = build_calibrated_trading_agents(pack)
    assert len(roster) == 17
    calibration_aware = [a for a in roster if isinstance(a, (CalibrationAwareVolatilityAgent, CalibrationAwareRegimeShiftAgent))]
    assert len(calibration_aware) == 2
