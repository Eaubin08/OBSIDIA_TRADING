"""
Obsidia Trading — Product Runtime (P1-D).

Facade produit stable au-dessus de la chaine Native deja existante :

    Market/Data -> Native agents -> NativeRosterAggregation
    -> NativeReferenceStrategy -> NativeReferenceSizing
    -> RealKX108Client -> KX108GovernanceBridge -> Binder
    -> PAPER execution -> Receipt/Proof -> Replay

Ce package n'implemente AUCUNE intelligence de trading : il assemble et
expose les composants deja construits dans `native/`, `execution/binder/`,
`governance/bridge/`, `proof/receipts/`. Voir `docs/MIGRATION_PROVENANCE.md`
(section P1-D) pour le detail des choix de conception.
"""
from __future__ import annotations

from runtime.config import RuntimeConfig
from runtime.obsidia_trading_runtime import ObsidiaTradingRuntime
from runtime.status import (
    CalibrationStatus,
    KX108Status,
    ModeStatus,
    ProofStatus,
    ReceiptStoreStatus,
    ReplayStatus,
    RuntimeStatus,
    SizingStatus,
)

__all__ = [
    "RuntimeConfig",
    "ObsidiaTradingRuntime",
    "RuntimeStatus",
    "KX108Status",
    "SizingStatus",
    "CalibrationStatus",
    "ProofStatus",
    "ModeStatus",
    "ReceiptStoreStatus",
    "ReplayStatus",
]
