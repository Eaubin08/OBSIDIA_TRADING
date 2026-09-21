"""
Obsidia Trading — persistance des receipts (chantier F7).

`ReceiptStore` implemente `domain.ports.proof.ProofPort` : c'est le port de
preuve que `execution/binder/engine.py::CycleEngine` invoque deja depuis F3
(`self.proof.record(receipt)` / `self.proof.last_hash()`). Aucune modification
du moteur n'est necessaire pour brancher ce store — seul
`execution/binder/paper_execution.py::build_paper_cycle_engine` recoit un
parametre optionnel `proof=` supplementaire (voir section F7 de
docs/MIGRATION_PROVENANCE.md).

Format sur disque (JSONL append-only, une ligne = un receipt) :

    {"stored_hash": "<sha256 du contenu hashable>", "receipt": {...as_dict()...}}

`stored_hash` est calcule a l'ECRITURE a partir du meme sous-ensemble de
champs que `CycleReceipt.decision_hash()` (voir `hashable_subset` ci-dessous)
et rejoue au moment de la lecture par `receipt_verify.py` : c'est ce qui
permet de detecter la modification d'un receipt meme s'il est le dernier de
la chaine (le chainage par `previous_receipt_hash` seul ne le detecterait
pas).

Ce module NE DECIDE RIEN. Il ne fait que persister et relire. Aucune methode
ne produit ni ne modifie une `Authority`/`Decision` — voir
tests/unit/test_receipt_chain.py::test_proof_is_not_authority.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from domain.receipt import GENESIS_HASH, CycleReceipt, canonical_json

# Cles du contenu hashable d'un CycleReceipt (domain/receipt.py::_hashable_content).
# Dupliquees ici deliberement : ce store ne doit pas dependre de l'implementation
# privee de CycleReceipt pour recalculer un hash sur des donnees deja serialisees.
_HASHABLE_KEYS = (
    "cycle_id",
    "parent_cycle_id",
    "receipt_schema_version",
    "decision_id",
    "mode",
    "state_fingerprint",
    "decision",
    "previous_receipt_hash",
    "execution_plan",
    "execution_result",
    "consequence",
    "degraded_reasons",
    "extensions",
)


class DuplicateCycleError(ValueError):
    """Un receipt portant le meme cycle_id est deja enregistre."""


class CorruptedReceiptLogError(ValueError):
    """Le journal JSONL contient une ligne illisible ou incoherente."""


def hashable_subset(receipt_as_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Sous-ensemble hashable d'un receipt deja serialise (`as_dict()`)."""
    return {key: receipt_as_dict.get(key) for key in _HASHABLE_KEYS}


def compute_stored_hash(receipt_as_dict: Dict[str, Any]) -> str:
    """
    Recalcule le hash d'integrite d'un receipt serialise.

    Identique par construction a `CycleReceipt.decision_hash()` : meme
    ensemble de cles, meme serialisation canonique, meme algorithme.
    """
    raw = canonical_json(hashable_subset(receipt_as_dict))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StoredCycleReceipt:
    """
    Modele de lecture d'un receipt persiste.

    DELIBEREMENT distinct de `domain.receipt.CycleReceipt` : reconstruire de
    vraies instances de `Decision`/`ActionProposal`/`ExecutionPlan`/
    `ExecutionResult` (six dataclasses imbriquees) depuis un JSON generique
    est hors perimetre de F7 et aurait ete fragile a batir dans le temps
    imparti. Aucune information n'est perdue pour autant : `raw` porte le
    dictionnaire complet (`as_dict()` d'origine), donc unknowns/
    contradictions/risk_flags/evidence/kx108_response/local_signal/
    simulation restent tous accessibles pour l'audit et le replay — cette
    dette est documentee dans docs/MIGRATION_PROVENANCE.md (section F7).
    """

    cycle_id: str
    decision_id: str
    receipt_schema_version: str
    previous_receipt_hash: str
    stored_hash: str
    authority: str
    mode: str
    degraded_reasons: tuple
    raw: Dict[str, Any] = field(repr=False)

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.raw)


class ReceiptStore:
    """
    Persistance JSONL append-only des receipts de cycle.

    Implemente le Protocol `domain.ports.proof.ProofPort` :
    `last_hash`, `record`, `read`, `history`.
    """

    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    # ── ProofPort ────────────────────────────────────────────────────────

    def last_hash(self) -> str:
        lines = self._read_raw_lines()
        if not lines:
            return GENESIS_HASH
        return lines[-1]["stored_hash"]

    def record(self, receipt: CycleReceipt) -> CycleReceipt:
        """
        Persiste `receipt` et retourne EXACTEMENT l'objet recu.

        Ce store n'enrichit jamais le receipt (contrairement a un futur
        decorateur ERC-8004 mentionne dans domain/ports/proof.py) : la
        version conservee et la version retournee a l'appelant sont
        identiques par construction.
        """
        as_dict = receipt.as_dict()
        cycle_id = as_dict["cycle_id"]

        existing_ids = {line["receipt"]["cycle_id"] for line in self._read_raw_lines()}
        if cycle_id in existing_ids:
            raise DuplicateCycleError(f"cycle_id deja enregistre: {cycle_id}")

        stored_hash = compute_stored_hash(as_dict)
        line = canonical_json({"stored_hash": stored_hash, "receipt": as_dict})

        # Ecriture atomique : append + flush + fsync explicite. Une ligne
        # JSONL est ecrite en une seule operation `write` ; flush+fsync
        # force le systeme a persister avant de rendre la main, ce qui
        # minimise (sans l'annuler completement, aucune methode POSIX ne le
        # garantit a 100% sur toutes les plateformes) le risque d'une ligne
        # partiellement ecrite en cas de crash immediatement apres l'appel.
        # Alternative ecartee : reecrire tout le fichier via un temporaire +
        # rename a chaque append aurait ete O(n) par ecriture et aurait perdu
        # la propriete append-only recherchee par la consigne.
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())

        return receipt

    def read(self, decision_id: str) -> Optional[StoredCycleReceipt]:
        for line in self._read_raw_lines():
            if line["receipt"]["decision_id"] == decision_id:
                return self._to_stored(line)
        return None

    def history(self, limit: int = 100) -> Sequence[StoredCycleReceipt]:
        lines = self._read_raw_lines()[-limit:] if limit else self._read_raw_lines()
        return tuple(self._to_stored(line) for line in lines)

    # ── Lectures additionnelles (hors ProofPort, utiles au replay) ───────

    def find_by_cycle_id(self, cycle_id: str) -> Optional[StoredCycleReceipt]:
        for line in self._read_raw_lines():
            if line["receipt"]["cycle_id"] == cycle_id:
                return self._to_stored(line)
        return None

    def all_raw_lines(self) -> List[Dict[str, Any]]:
        """Lignes brutes (stored_hash + receipt dict), dans l'ordre d'ecriture."""
        return self._read_raw_lines()

    # ── Internes ─────────────────────────────────────────────────────────

    def _read_raw_lines(self) -> List[Dict[str, Any]]:
        text = self.path.read_text(encoding="utf-8")
        if not text.strip():
            return []
        records: List[Dict[str, Any]] = []
        for lineno, raw_line in enumerate(text.splitlines(), start=1):
            if not raw_line.strip():
                continue
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise CorruptedReceiptLogError(
                    f"ligne {lineno} illisible (JSON malforme): {exc}"
                ) from exc
            if "stored_hash" not in payload or "receipt" not in payload:
                raise CorruptedReceiptLogError(
                    f"ligne {lineno} incomplete: champs 'stored_hash'/'receipt' manquants"
                )
            records.append(payload)
        return records

    @staticmethod
    def _to_stored(line: Dict[str, Any]) -> StoredCycleReceipt:
        receipt = line["receipt"]
        return StoredCycleReceipt(
            cycle_id=receipt["cycle_id"],
            decision_id=receipt["decision_id"],
            receipt_schema_version=receipt["receipt_schema_version"],
            previous_receipt_hash=receipt["previous_receipt_hash"],
            stored_hash=line["stored_hash"],
            authority=receipt["decision"]["authority"],
            mode=receipt["mode"],
            degraded_reasons=tuple(receipt.get("degraded_reasons", ())),
            raw=receipt,
        )
