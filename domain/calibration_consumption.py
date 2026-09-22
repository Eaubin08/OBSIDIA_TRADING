"""
F13.1 — Consommation du CalibrationPack par les agents Trading pertinents.

Regle absolue : ce module ne lit et n'importe RIEN depuis governance/ ni
execution/binder/ — la calibration precede et ignore totalement l'autorite
(verifie par tests/unit/test_calibration_consumption.py::test_no_kernel_import).

Un CalibrationPack calibre sur un symbole/fenetre donne n'est PAS valable
silencieusement pour un autre symbole ni au-dela d'une fenetre raisonnable.
Toute incompatibilite doit etre explicite (CompatibilityStatus), jamais
une application silencieuse.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from domain.calibration import (
    CalibrationPack,
    DatasetDescriptor,
    ModelCalibration,
    ModelCalibrationStatus,
)
from domain.calibration_estimation import (
    estimate_garch_1_1,
    estimate_markov_regime_matrix,
    estimate_realized_volatility,
)


class CompatibilityStatus(str, Enum):
    COMPATIBLE = "COMPATIBLE"
    NO_PACK = "NO_PACK"
    SYMBOL_MISMATCH = "SYMBOL_MISMATCH"
    STALE = "STALE"
    NOT_CALIBRATED = "NOT_CALIBRATED"


@dataclass(frozen=True)
class CompatibilityCheck:
    status: CompatibilityStatus
    reason: str

    @property
    def usable(self) -> bool:
        return self.status is CompatibilityStatus.COMPATIBLE


def check_compatibility(
    pack: Optional[CalibrationPack],
    symbol: str,
    *,
    max_age_days: Optional[float] = None,
    now: Optional[datetime] = None,
) -> CompatibilityCheck:
    """
    Verifie qu'un CalibrationPack peut etre applique a `symbol` maintenant.

    Ne devine jamais une compatibilite : un pack absent, un symbole
    different, un statut NOT_CALIBRATED_NO_REAL_DATA, ou un pack trop
    ancien (si `max_age_days` est fourni) produisent tous un refus
    explicite plutot qu'une utilisation silencieuse.
    """
    if pack is None:
        return CompatibilityCheck(CompatibilityStatus.NO_PACK, "aucun CalibrationPack fourni")

    if pack.dataset.symbol.upper() != symbol.upper():
        return CompatibilityCheck(
            CompatibilityStatus.SYMBOL_MISMATCH,
            f"pack calibre sur {pack.dataset.symbol!r}, demande pour {symbol!r}",
        )

    from domain.calibration import CalibrationStatus

    if pack.status is CalibrationStatus.NOT_CALIBRATED_NO_REAL_DATA:
        return CompatibilityCheck(
            CompatibilityStatus.NOT_CALIBRATED,
            "pack.status = NOT_CALIBRATED_NO_REAL_DATA (aucune donnee reelle)",
        )

    if max_age_days is not None:
        now = now or datetime.now(timezone.utc)
        try:
            created = datetime.fromisoformat(pack.created_at)
        except ValueError:
            return CompatibilityCheck(
                CompatibilityStatus.STALE, f"created_at illisible: {pack.created_at!r}"
            )
        age_days = (now - created).total_seconds() / 86400.0
        if age_days > max_age_days:
            return CompatibilityCheck(
                CompatibilityStatus.STALE,
                f"pack age de {age_days:.1f}j > max_age_days={max_age_days}",
            )

    return CompatibilityCheck(CompatibilityStatus.COMPATIBLE, "symbole/fraicheur/statut ok")


def evidence_refs_for_pack(pack: CalibrationPack) -> list:
    """Provenance minimale a attacher a un AgentOutput/AgentVote — jamais le pack entier."""
    return [
        f"calibration_id={pack.calibration_id}",
        f"dataset_digest={pack.dataset.digest()}",
        f"calibration_schema_version={pack.schema_version}",
    ]


def calibrated_daily_volatility_fallback(pack: CalibrationPack) -> Optional[float]:
    """
    Volatilite journaliere derivee du modele 'realized_volatility' calibre
    (desannualisee via /sqrt(252)) — utilisable UNIQUEMENT comme fallback
    quand l'historique de prix local est trop court pour un calcul fiable,
    jamais pour remplacer un calcul local valide.
    """
    model = pack.model("realized_volatility")
    if model is None or model.status is ModelCalibrationStatus.UNCALIBRATED:
        return None
    annualized = model.parameters.get("annualized_vol")
    if annualized is None or annualized <= 0:
        return None
    return annualized / (252.0 ** 0.5)


def garch_calibration_note(pack: CalibrationPack) -> Optional[str]:
    """
    Note d'evidence textuelle sur l'etat de calibration GARCH(1,1) —
    jamais utilisee pour recalculer un verdict, uniquement tracee jusqu'au
    receipt via evidence_refs.
    """
    model = pack.model("garch_1_1")
    if model is None:
        return None
    if model.status is ModelCalibrationStatus.UNCALIBRATED:
        return f"garch_1_1=UNCALIBRATED ({model.method})"
    omega = model.parameters.get("omega")
    alpha = model.parameters.get("alpha")
    beta = model.parameters.get("beta")
    return (
        f"garch_1_1={model.status.value} omega={omega} alpha={alpha} beta={beta} "
        f"calibration_id={pack.calibration_id}"
    )


def markov_calibration_note(pack: CalibrationPack) -> Optional[str]:
    """Note d'evidence textuelle sur l'etat de la calibration Markov, jamais une decision."""
    model = pack.model("markov_regime_matrix")
    if model is None:
        return None
    if model.status is ModelCalibrationStatus.UNCALIBRATED:
        return f"markov_regime_matrix=UNCALIBRATED ({model.method})"
    return f"markov_regime_matrix={model.status.value} sample={model.parameters.get('sample_size')}"


def build_full_real_calibration_pack(
    dataset: DatasetDescriptor, returns: list, *, n_regimes: int = 2
) -> CalibrationPack:
    """
    F13.1 — assemble le CalibrationPack complet (realized_volatility +
    garch_1_1 + markov_regime_matrix) a partir de rendements reels.

    F13 avait deja les 3 fonctions d'estimation pures (domain/
    calibration_estimation.py) mais ne les assemblait jamais toutes les
    trois dans un CalibrationPack reellement construit (seul
    realized_volatility etait attache) — combleee ici. Chaque modele
    insuffisant reste honnetement UNCALIBRATED, jamais invente.
    """
    vol = estimate_realized_volatility(returns)
    vol_model = ModelCalibration(
        model_name="realized_volatility",
        status=(
            ModelCalibrationStatus.CALIBRATED
            if vol.sufficient_data
            else ModelCalibrationStatus.UNCALIBRATED
        ),
        method=vol.method,
        parameters={"annualized_vol": vol.annualized_vol, "sample_size": float(vol.sample_size)},
    )

    garch = estimate_garch_1_1(returns)
    garch_model = ModelCalibration(
        model_name="garch_1_1",
        status=(
            ModelCalibrationStatus.CALIBRATED
            if garch.sufficient_data
            else ModelCalibrationStatus.UNCALIBRATED
        ),
        method=garch.method,
        parameters={
            "omega": garch.omega, "alpha": garch.alpha, "beta": garch.beta,
            "sample_size": float(garch.sample_size),
        },
    )

    markov = estimate_markov_regime_matrix(returns, n_regimes=n_regimes)
    markov_params = {
        "n_regimes": float(markov.n_regimes),
        "sample_size": float(sum(markov.observations_per_regime)) if markov.observations_per_regime else 0.0,
    }
    for i, row in enumerate(markov.transition_matrix):
        for j, p in enumerate(row):
            markov_params[f"p_{i}_{j}"] = p
    for i, cnt in enumerate(markov.observations_per_regime):
        markov_params[f"obs_regime_{i}"] = float(cnt)
    markov_model = ModelCalibration(
        model_name="markov_regime_matrix",
        status=(
            ModelCalibrationStatus.CALIBRATED
            if markov.sufficient_data
            else ModelCalibrationStatus.UNCALIBRATED
        ),
        method=markov.method,
        parameters=markov_params,
    )

    return CalibrationPack.build(
        dataset=dataset,
        models=(vol_model, garch_model, markov_model),
        method="f13_1_full_real_v1",
    )
