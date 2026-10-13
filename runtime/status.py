"""
RuntimeStatus — etat produit du Reference Runtime, par sous-systeme (P1-D).

Regle imperative (chantier P1-D section I) : jamais un booleen global
"healthy". Chaque sous-systeme est inspectable independamment ; un runtime
degrade sur un axe (ex: SIZING=NOT_CONFIGURED) reste parfaitement observable
sur tous les autres.

KX108Status distingue explicitement configuration et observation reelle
(meme principe que Cockpit V2 Phase A2) : `REAL_CLIENT_CONFIGURED` ne
signifie PAS que le Kernel a repondu — seule une evidence de cycle reelle
(`kx108_response` sans `fail_closed` et avec `source == "KX108_REAL"`) fait
passer a `REAL_OBSERVED`.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class KX108Status(str, Enum):
    REAL_CLIENT_CONFIGURED = "REAL_CLIENT_CONFIGURED"
    REAL_OBSERVED = "REAL_OBSERVED"
    UNAVAILABLE = "UNAVAILABLE"


class SizingStatus(str, Enum):
    CONFIGURED = "CONFIGURED"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class CalibrationStatus(str, Enum):
    CONFIGURED = "CONFIGURED"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class ProofStatus(str, Enum):
    REQUIRED = "REQUIRED"


class ModeStatus(str, Enum):
    PAPER = "PAPER"


class ReceiptStoreStatus(str, Enum):
    CONFIGURED = "CONFIGURED"
    UNAVAILABLE = "UNAVAILABLE"


class ReplayStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class MarketStatus(str, Enum):
    NOT_OBSERVED = "NOT_OBSERVED"
    OBSERVED = "OBSERVED"
    DEGRADED = "DEGRADED"


class AgentsStatus(str, Enum):
    NATIVE_17 = "NATIVE_17"
    NATIVE_17_CALIBRATED = "NATIVE_17_CALIBRATED"


class BinderStatus(str, Enum):
    ACTIVE = "ACTIVE"


class StrategyStatus(str, Enum):
    NATIVE_REFERENCE = "NATIVE_REFERENCE"


@dataclass(frozen=True)
class RuntimeStatus:
    """
    Photographie en lecture seule de l'etat du runtime au moment de l'appel.

    Chaque champ reflete un sous-systeme independant. `kx108`/`market`
    peuvent evoluer entre deux appels de `status()` uniquement en reponse a
    une evidence de cycle reellement observee (jamais une supposition).
    """

    market: MarketStatus
    agents: AgentsStatus
    calibration: CalibrationStatus
    strategy: StrategyStatus
    sizing: SizingStatus
    kx108: KX108Status
    binder: BinderStatus
    mode: ModeStatus
    proof: ProofStatus
    receipt_store: ReceiptStoreStatus
    replay: ReplayStatus

    def as_dict(self) -> dict:
        return {
            "market": self.market.value,
            "agents": self.agents.value,
            "calibration": self.calibration.value,
            "strategy": self.strategy.value,
            "sizing": self.sizing.value,
            "kx108": self.kx108.value,
            "binder": self.binder.value,
            "mode": self.mode.value,
            "proof": self.proof.value,
            "receipt_store": self.receipt_store.value,
            "replay": self.replay.value,
        }
