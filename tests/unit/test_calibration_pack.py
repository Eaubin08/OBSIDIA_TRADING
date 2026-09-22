"""
F13 — Real Trading Domain Calibration.

Cette machine n'a jamais eu de credentials Alpaca reels configures (verifie
par attempt_real_historical_dataset ci-dessous, qui retourne
NO_CREDENTIALS_CONFIGURED). Aucune donnee de marche reelle n'est donc
disponible dans cet environnement : ces tests prouvent que
l'infrastructure de calibration est deterministe, honnete sur l'absence de
donnees reelles, et ne fabrique jamais de valeur synthetique presentee
comme reelle. Ils ne pretendent pas prouver une calibration reelle
obtenue — F13 reste NOT_CLOSED tant qu'aucune vraie donnee n'est
accessible (voir docs/MIGRATION_PROVENANCE.md, section F13).
"""
from __future__ import annotations

import ast
from pathlib import Path

from domain.calibration import (
    CalibrationPack,
    CalibrationStatus,
    DatasetDescriptor,
    ModelCalibration,
    ModelCalibrationStatus,
)
from market.adapters.alpaca.real_dataset_attempt import attempt_real_historical_dataset


def _no_data_descriptor(quality_flag: str = "NO_CREDENTIALS_CONFIGURED") -> DatasetDescriptor:
    return DatasetDescriptor(
        source="alpaca_market_data_api", symbol="AAPL", timeframe="1Day",
        start=None, end=None, observation_count=0,
        retrieved_at="2026-09-22T00:00:00+00:00", quality_flags=(quality_flag,),
    )


def _real_like_descriptor(count: int = 100) -> DatasetDescriptor:
    return DatasetDescriptor(
        source="alpaca_market_data_api", symbol="AAPL", timeframe="1Day",
        start="2026-01-01", end="2026-06-01", observation_count=count,
        retrieved_at="2026-09-22T00:00:00+00:00", quality_flags=(),
    )


def _uncalibrated_models() -> tuple:
    return (
        ModelCalibration(
            model_name="markov_regime_matrix", status=ModelCalibrationStatus.UNCALIBRATED,
            method="build_regime_matrix (F4, auto-transition artificielle, jamais fittee sur donnees)",
        ),
        ModelCalibration(
            model_name="garch_1_1", status=ModelCalibrationStatus.UNCALIBRATED,
            method="parametres fixes (omega/alpha/beta passes en dur a MarketProcessParams, aucun fitting)",
        ),
    )


# 1. calibration deterministe
def test_calibration_pack_is_deterministic():
    ds = _no_data_descriptor()
    p1 = CalibrationPack.build(dataset=ds, models=_uncalibrated_models(), method="v1")
    p2 = CalibrationPack.build(dataset=ds, models=_uncalibrated_models(), method="v1")
    assert p1.parameters_digest == p2.parameters_digest
    assert p1.calibration_id == p2.calibration_id


# 2. meme dataset -> meme digest
def test_same_dataset_same_digest():
    ds1 = _real_like_descriptor(100)
    ds2 = _real_like_descriptor(100)
    assert ds1.digest() == ds2.digest()


# 3. dataset different -> digest different
def test_different_dataset_different_digest():
    ds1 = _real_like_descriptor(100)
    ds2 = _real_like_descriptor(150)
    assert ds1.digest() != ds2.digest()
    p1 = CalibrationPack.build(dataset=ds1, models=(), method="v1")
    p2 = CalibrationPack.build(dataset=ds2, models=(), method="v1")
    assert p1.parameters_digest != p2.parameters_digest


# 4. provenance conservee
def test_provenance_preserved_in_pack():
    ds = _real_like_descriptor(42)
    pack = CalibrationPack.build(dataset=ds, models=(), method="v1")
    d = pack.as_dict()
    assert d["dataset"]["observation_count"] == 42
    assert d["dataset"]["source"] == "alpaca_market_data_api"
    assert d["dataset_digest"] == ds.digest()


# 5. donnees insuffisantes -> statut explicite, jamais une valeur inventee
def test_no_real_data_yields_explicit_not_calibrated_status():
    ds = _no_data_descriptor()
    pack = CalibrationPack.build(dataset=ds, models=_uncalibrated_models(), method="v1")
    assert pack.status is CalibrationStatus.NOT_CALIBRATED_NO_REAL_DATA
    assert not ds.is_real


# 6. staleness identifiable
def test_staleness_fields_present():
    ds = _real_like_descriptor()
    pack = CalibrationPack.build(dataset=ds, models=(), method="v1")
    d = pack.as_dict()
    assert d["created_at"]
    assert d["dataset"]["retrieved_at"]


# 7. Markov statut honnete NON_CALIBRATED (dette connue F4, jamais masquee)
def test_markov_model_marked_uncalibrated_honestly():
    pack = CalibrationPack.build(
        dataset=_real_like_descriptor(), models=_uncalibrated_models(), method="v1",
    )
    markov = pack.model("markov_regime_matrix")
    assert markov is not None
    assert markov.status is ModelCalibrationStatus.UNCALIBRATED


def test_garch_model_marked_uncalibrated_honestly():
    pack = CalibrationPack.build(
        dataset=_real_like_descriptor(), models=_uncalibrated_models(), method="v1",
    )
    garch = pack.model("garch_1_1")
    assert garch is not None
    assert garch.status is ModelCalibrationStatus.UNCALIBRATED


# 8. aucun fallback synthetique silencieux : verifie que le dataset attempt
#    honnete retourne bien observation_count=0 dans CET environnement (pas
#    de credentials), jamais une valeur non nulle inventee.
def test_real_dataset_attempt_is_honest_about_missing_credentials():
    ds = attempt_real_historical_dataset(symbol="AAPL", timeframe="1Day", limit=5)
    assert ds.observation_count == 0
    assert "NO_CREDENTIALS_CONFIGURED" in ds.quality_flags
    assert not ds.is_real


# 9. Native fonctionne avec CalibrationPack (le pack peut etre construit et
#    interroge independamment du roster natif, sans le modifier)
def test_calibration_pack_usable_independently_of_native_roster():
    pack = CalibrationPack.build(dataset=_no_data_descriptor(), models=(), method="v1")
    assert pack.status is CalibrationStatus.NOT_CALIBRATED_NO_REAL_DATA
    # Le roster natif (F3) n'a pas ete modifie par F13 : aucune dependance
    # vers domain.calibration dans native/agents/domains/trading_agents.py.
    src = Path("native/agents/domains/trading_agents.py").read_text(encoding="utf-8")
    assert "calibration" not in src.lower()


# 10. External n'est pas oblige d'utiliser la calibration Native : le
#     module external/ ne depend pas de domain.calibration.
def test_external_path_not_coupled_to_calibration_pack():
    for path in Path("external").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        src = path.read_text(encoding="utf-8")
        assert "domain.calibration" not in src, f"{path} depend de domain.calibration"


# 11. convergence canonique intacte : to_canonical_agent_signal (F3.5/F8.7)
#     n'a pas ete modifie par F13.
def test_canonical_builder_untouched_by_f13():
    src = Path("domain/contracts/canonical.py").read_text(encoding="utf-8")
    assert "calibration" not in src.lower()


# 17. aucun tuning selon verdict Kernel : domain/calibration.py et
#     market/adapters/alpaca/real_dataset_attempt.py n'importent jamais
#     governance/ ni execution/binder/ (verification AST, pas juste texte).
def test_no_kernel_verdict_import_in_calibration_code():
    for relpath in ("domain/calibration.py", "market/adapters/alpaca/real_dataset_attempt.py"):
        tree = ast.parse(Path(relpath).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [n.name for n in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                assert not name.startswith("governance"), f"{relpath} importe {name}"
                assert not name.startswith("execution.binder"), f"{relpath} importe {name}"
