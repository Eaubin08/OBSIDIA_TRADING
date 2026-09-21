"""
Obsidia Trading — decision et preuve (chantier §12 / §23).

Deux objets :

    Decision      le verdict de X-108 et ce qui l'a motive
    CycleReceipt  la trace auditable complete d'un cycle

Points structurants par rapport au prototype :

  - ACT, HOLD et BLOCK produisent TOUS un receipt. Une abstention est une
    decision, et elle se prouve au meme titre qu'une action.
  - Les receipts sont CHAINES par `previous_receipt_hash`. Le prototype
    produisait des hash independants : retirer un cycle du journal passait
    inapercu. Ici, toute rupture de chaine est detectable.
  - Le hash est calcule sur un contenu ou l'horodatage est isole, de sorte
    qu'un rejeu du meme etat produise le meme `decision_hash`.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from domain.orders import ExecutionPlan, ExecutionResult
from domain.proposal import ActionProposal
from domain.types import Authority, Mode

GENESIS_HASH = "0" * 64
RECEIPT_SCHEMA_VERSION = "receipt.v1"


@dataclass(frozen=True)
class Decision:
    """
    Verdict de X-108 sur une proposition.

    `authority` est la seule chose qui autorise la suite. `reason` doit rester
    lisible par un humain : c'est ce que le cockpit affiche et ce que l'audit
    relit.
    """

    decision_id: str
    authority: Authority
    reason: str
    proposal: ActionProposal
    structural_score: Optional[float] = None
    risk_score: Optional[float] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    rules_evaluated: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def authorizes_action(self) -> bool:
        return self.authority.authorizes_irreversible_action

    def as_dict(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "authority": self.authority.value,
            "authority_legacy": self.authority.to_legacy(),
            "reason": self.reason,
            "structural_score": self.structural_score,
            "risk_score": self.risk_score,
            "metrics": self.metrics,
            "rules_evaluated": list(self.rules_evaluated),
            "proposal": self.proposal.as_dict(),
        }


@dataclass(frozen=True)
class CycleReceipt:
    """
    Trace auditable d'un cycle complet, du monde observe a sa consequence.

    Repond a la question : « sur quoi le systeme s'est-il appuye, qu'a-t-il
    envisage, qu'a-t-il decide, pourquoi, qu'a-t-il fait, et qu'est-il
    arrive ensuite ». Emis pour ACT, HOLD et BLOCK sans distinction.
    """

    cycle_id: str
    decision_id: str
    recorded_at: float
    mode: Mode
    state_fingerprint: str
    decision: Decision
    previous_receipt_hash: str = GENESIS_HASH
    parent_cycle_id: Optional[str] = None
    receipt_schema_version: str = RECEIPT_SCHEMA_VERSION
    execution_plan: Optional[ExecutionPlan] = None
    execution_result: Optional[ExecutionResult] = None
    consequence: Dict[str, Any] = field(default_factory=dict)
    degraded_reasons: Tuple[str, ...] = field(default_factory=tuple)
    extensions: Dict[str, Any] = field(default_factory=dict)

    def _hashable_content(self) -> dict:
        """
        Contenu servant au calcul du hash.

        `recorded_at` en est volontairement exclu : le hash identifie ce qui a
        ete decide, pas le moment ou la ligne a ete ecrite. C'est cette
        exclusion qui rend le rejeu verifiable (chantier §25) — le prototype
        incluait un timestamp et ne pouvait donc pas satisfaire cette
        propriete.
        """
        return {
            "cycle_id": self.cycle_id,
            "parent_cycle_id": self.parent_cycle_id,
            "receipt_schema_version": self.receipt_schema_version,
            "decision_id": self.decision_id,
            "mode": self.mode.value,
            "state_fingerprint": self.state_fingerprint,
            "decision": self.decision.as_dict(),
            "previous_receipt_hash": self.previous_receipt_hash,
            "execution_plan": self.execution_plan.as_dict() if self.execution_plan else None,
            "execution_result": (
                self.execution_result.as_dict() if self.execution_result else None
            ),
            "consequence": self.consequence,
            "degraded_reasons": list(self.degraded_reasons),
            "extensions": self.extensions,
        }

    def decision_hash(self) -> str:
        raw = canonical_json(self._hashable_content())
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def integrity_hash(self) -> str:
        """Alias honnete : hash d'integrite local, pas signature externe."""
        return self.decision_hash()

    def receipt_hash(self) -> str:
        """Nom explicite pour la chaine locale de receipts."""
        return self.decision_hash()

    @property
    def touched_the_market(self) -> bool:
        """
        Vrai si ce cycle a effectivement envoye quelque chose au broker.

        C'est la propriete verifiee par les invariants de gouvernance : elle
        doit etre fausse pour tout receipt dont l'autorite n'est pas ACT.
        """
        return bool(self.execution_result and self.execution_result.touched_the_market)

    def as_dict(self) -> dict:
        content = self._hashable_content()
        content["recorded_at"] = self.recorded_at
        content["decision_hash"] = self.decision_hash()
        content["integrity_hash"] = self.integrity_hash()
        content["receipt_hash"] = self.receipt_hash()
        content["touched_the_market"] = self.touched_the_market
        return content

    def follows(self, previous: Optional["CycleReceipt"]) -> bool:
        """Verifie le chainage avec le receipt precedent."""
        expected = previous.decision_hash() if previous else GENESIS_HASH
        return self.previous_receipt_hash == expected


def verify_chain(receipts: Tuple[CycleReceipt, ...]) -> Tuple[bool, Optional[str]]:
    """
    Verifie l'integrite d'une chaine de receipts.

    Retourne (valide, raison_de_rupture). Detecte aussi bien une alteration de
    contenu qu'un cycle retire du journal.
    """
    previous: Optional[CycleReceipt] = None
    for receipt in receipts:
        if not receipt.follows(previous):
            return False, (
                f"rupture de chaine au cycle {receipt.cycle_id} : "
                f"attendu {previous.decision_hash() if previous else GENESIS_HASH}, "
                f"trouve {receipt.previous_receipt_hash}"
            )
        previous = receipt
    return True, None


def canonical_json(payload: Any) -> str:
    """Serialisation canonique locale pour les hashes d'integrite."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
