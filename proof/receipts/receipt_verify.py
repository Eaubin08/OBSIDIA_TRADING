"""
Obsidia Trading — verification d'integrite de la chaine de receipts (F7).

Ce module ne repare JAMAIS silencieusement une chaine cassee : il retourne
un etat explicite (`IntegrityStatus`) et, en cas d'anomalie, la premiere
anomalie rencontree (pas un resume vague). Il ne decide rien et ne modifie
rien — voir tests/unit/test_receipt_chain.py::test_proof_is_not_authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Union

from domain.receipt import GENESIS_HASH, RECEIPT_SCHEMA_VERSION
from proof.receipts.receipt_store import (
    CorruptedReceiptLogError,
    ReceiptStore,
    compute_stored_hash,
)


class IntegrityStatus(str, Enum):
    EMPTY = "EMPTY"
    VALID = "VALID"
    CORRUPTED = "CORRUPTED"


@dataclass(frozen=True)
class IntegrityReport:
    status: IntegrityStatus
    checked_count: int
    first_error: Optional[str] = None
    first_error_index: Optional[int] = None

    @property
    def is_valid(self) -> bool:
        return self.status in (IntegrityStatus.VALID, IntegrityStatus.EMPTY)


class ReceiptChainVerifier:
    """Verifie l'integrite d'une chaine de receipts persistee par `ReceiptStore`."""

    def verify_store(self, store: ReceiptStore) -> IntegrityReport:
        try:
            lines = store.all_raw_lines()
        except CorruptedReceiptLogError as exc:
            return IntegrityReport(
                status=IntegrityStatus.CORRUPTED,
                checked_count=0,
                first_error=str(exc),
                first_error_index=0,
            )
        return self.verify_lines(lines)

    def verify_path(self, path: Union[str, Path]) -> IntegrityReport:
        return self.verify_store(ReceiptStore(path))

    def verify_lines(self, lines) -> IntegrityReport:
        if not lines:
            return IntegrityReport(status=IntegrityStatus.EMPTY, checked_count=0)

        seen_cycle_ids: set = set()
        previous_stored_hash = GENESIS_HASH

        for index, line in enumerate(lines):
            receipt = line.get("receipt")
            stored_hash = line.get("stored_hash")

            if receipt is None or stored_hash is None:
                return self._corrupted(
                    index, f"ligne {index} incomplete (receipt/stored_hash manquant)"
                )

            version = receipt.get("receipt_schema_version")
            if version != RECEIPT_SCHEMA_VERSION:
                return self._corrupted(
                    index,
                    f"cycle {receipt.get('cycle_id')} : receipt_schema_version "
                    f"inconnu ({version!r}), attendu {RECEIPT_SCHEMA_VERSION!r} "
                    "- refus d'interpreter plutot que de deviner le format",
                )

            cycle_id = receipt.get("cycle_id")
            if cycle_id in seen_cycle_ids:
                return self._corrupted(
                    index, f"cycle_id duplique detecte: {cycle_id!r} (position {index})"
                )
            seen_cycle_ids.add(cycle_id)

            recomputed = compute_stored_hash(receipt)
            if recomputed != stored_hash:
                return self._corrupted(
                    index,
                    f"cycle {cycle_id!r} altere : hash recalcule {recomputed[:12]} "
                    f"!= hash stocke {stored_hash[:12]} (contenu modifie apres ecriture)",
                )

            expected_previous = receipt.get("previous_receipt_hash")
            if expected_previous != previous_stored_hash:
                return self._corrupted(
                    index,
                    f"rupture de chaine au cycle {cycle_id!r} (position {index}) : "
                    f"previous_receipt_hash={expected_previous!r}, "
                    f"attendu {previous_stored_hash!r} "
                    "(receipt supprime, reordonne, ou chaine tronquee)",
                )

            previous_stored_hash = stored_hash

        return IntegrityReport(status=IntegrityStatus.VALID, checked_count=len(lines))

    @staticmethod
    def _corrupted(index: int, message: str) -> IntegrityReport:
        return IntegrityReport(
            status=IntegrityStatus.CORRUPTED,
            checked_count=index,
            first_error=message,
            first_error_index=index,
        )
