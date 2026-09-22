"""
F13 — Domain calibration artifact (CalibrationPack).

REGLE ABSOLUE : ce module ne calibre JAMAIS en fonction d'un verdict KX108.
Il n'importe rien depuis governance/ ni execution/binder/ (verifie par
tests/unit/test_calibration_pack.py::test_no_kernel_verdict_import).

Un CalibrationPack decrit ce qui a ete estime, sur quelles donnees, avec
quelle methode — jamais une decision. `status` doit etre honnete : si
aucune donnee de marche reelle n'a pu etre obtenue, le pack le dit
explicitement (NOT_CALIBRATED_NO_REAL_DATA) plutot que d'inventer des
parametres.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Tuple


SCHEMA_VERSION = "calibration.v1"


class CalibrationStatus(str, Enum):
    NOT_CALIBRATED_NO_REAL_DATA = "NOT_CALIBRATED_NO_REAL_DATA"
    PARTIALLY_CALIBRATED = "PARTIALLY_CALIBRATED"
    CALIBRATED = "CALIBRATED"


class ModelCalibrationStatus(str, Enum):
    UNCALIBRATED = "UNCALIBRATED"
    PARTIALLY_CALIBRATED = "PARTIALLY_CALIBRATED"
    CALIBRATED = "CALIBRATED"


@dataclass(frozen=True)
class DatasetDescriptor:
    """
    Provenance d'un dataset reel. Si `observation_count` est 0, c'est que
    la tentative d'obtention de donnees reelles a echoue — `quality_flags`
    doit alors contenir la raison exacte (jamais silencieuse).
    """

    source: str
    symbol: str
    timeframe: str
    start: Optional[str]
    end: Optional[str]
    observation_count: int
    retrieved_at: str
    quality_flags: Tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "start": self.start,
            "end": self.end,
            "observation_count": self.observation_count,
            "retrieved_at": self.retrieved_at,
            "quality_flags": list(self.quality_flags),
        }

    def digest(self) -> str:
        canonical = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @property
    def is_real(self) -> bool:
        """Vrai seulement si au moins une observation reelle a ete obtenue."""
        return self.observation_count > 0 and self.source not in ("", "NONE", "SYNTHETIC")


@dataclass(frozen=True)
class ModelCalibration:
    """Statut de calibration d'un modele individuel (GARCH, Markov, ...)."""

    model_name: str
    status: ModelCalibrationStatus
    method: str
    parameters: Dict[str, float] = field(default_factory=dict)
    calibration_window: Optional[str] = None
    notes: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "status": self.status.value,
            "method": self.method,
            "parameters": dict(self.parameters),
            "calibration_window": self.calibration_window,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class CalibrationPack:
    """
    Artefact de calibration reproductible (F13).

    Meme dataset + meme methode + memes parametres -> meme
    `parameters_digest`. `status` global reflete honnetement l'etat reel :
    NOT_CALIBRATED_NO_REAL_DATA si aucun dataset reel n'a pu etre obtenu.
    """

    calibration_id: str
    schema_version: str
    dataset: DatasetDescriptor
    models: Tuple[ModelCalibration, ...]
    method: str
    created_at: str
    status: CalibrationStatus

    @classmethod
    def build(
        cls,
        *,
        dataset: DatasetDescriptor,
        models: Tuple[ModelCalibration, ...],
        method: str,
    ) -> "CalibrationPack":
        created_at = datetime.now(timezone.utc).isoformat()
        if not dataset.is_real:
            status = CalibrationStatus.NOT_CALIBRATED_NO_REAL_DATA
        elif any(m.status is ModelCalibrationStatus.UNCALIBRATED for m in models):
            status = CalibrationStatus.PARTIALLY_CALIBRATED
        else:
            status = CalibrationStatus.CALIBRATED

        payload = {
            "schema_version": SCHEMA_VERSION,
            "dataset_digest": dataset.digest(),
            "models": [m.as_dict() for m in models],
            "method": method,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        parameters_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        calibration_id = f"calib-{parameters_digest[:16]}"

        return cls(
            calibration_id=calibration_id,
            schema_version=SCHEMA_VERSION,
            dataset=dataset,
            models=models,
            method=method,
            created_at=created_at,
            status=status,
        )

    @property
    def parameters_digest(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "dataset_digest": self.dataset.digest(),
            "models": [m.as_dict() for m in self.models],
            "method": self.method,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def as_dict(self) -> Dict[str, Any]:
        return {
            "calibration_id": self.calibration_id,
            "schema_version": self.schema_version,
            "dataset": self.dataset.as_dict(),
            "dataset_digest": self.dataset.digest(),
            "models": [m.as_dict() for m in self.models],
            "method": self.method,
            "created_at": self.created_at,
            "status": self.status.value,
            "parameters_digest": self.parameters_digest,
        }

    def model(self, name: str) -> Optional[ModelCalibration]:
        for m in self.models:
            if m.model_name == name:
                return m
        return None
