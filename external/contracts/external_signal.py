"""
Obsidia Trading — ExternalSignal (chantier F8, External Stack Adapter).

Format d'entree generique qu'une stack Trading tierce doit fournir. C'est
volontairement PLUS PAUVRE et DIFFERENT du vocabulaire interne
(`domain.proposal.AgentOutput`) : une entreprise ou un individu qui branche
sa propre stack (agents, regles, modele, operateur) ne doit jamais avoir a
connaitre le vocabulaire interne d'Obsidia. C'est le role du normalizer
(`external/normalization/normalizer.py`) de traduire ceci vers le contrat
canonique — jamais l'inverse.

ARBITRARY EXTERNAL STACK
    -> validation        (ExternalSignal.from_raw_payload, ce module)
    -> normalization      (external/normalization/normalizer.py)
    -> provenance preservation
    -> Canonical Domain Contract (domain/contracts/canonical.py, F3.5)
    -> same Governance Bridge (F5, inchange)
    -> same KX108
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

REQUIRED_FIELDS = ("source_id", "organization_id", "signal", "confidence", "rationale")


class InvalidExternalSignal(ValueError):
    """
    Un payload externe ne porte pas les champs minimums requis.

    Leve explicitement plutot que de deviner une valeur manquante (chantier
    §30, deja applique a `domain.types.Provenance` et
    `domain.provenance.SourceProvenance`) : une confiance ou un signal
    absent ne doit JAMAIS etre invente.
    """


@dataclass(frozen=True)
class ExternalSignal:
    """
    Signal brut, deja valide, en provenance d'une stack externe.

    `unknowns`/`contradictions`/`risk_flags` sont optionnels : si la stack
    externe ne les fournit pas, ils restent des tuples vides. C'est une
    limite documentee (pas une garantie) — un tuple vide signifie ici
    "non rapporte par la source", PAS "verifie comme absent". Voir
    docs/MIGRATION_PROVENANCE.md, section F8, pour la distinction.
    """

    source_id: str
    organization_id: str
    signal: str
    confidence: float
    rationale: str
    category: str = "EXTERNAL"
    adapter_id: Optional[str] = None
    original_event_id: Optional[str] = None
    observed_at: Optional[float] = None
    unknowns: Tuple[str, ...] = field(default_factory=tuple)
    contradictions: Tuple[str, ...] = field(default_factory=tuple)
    risk_flags: Tuple[str, ...] = field(default_factory=tuple)
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)
    raw_payload: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw_payload(cls, payload: Dict[str, Any]) -> "ExternalSignal":
        """
        Etape de VALIDATION du diagramme F8.

        Rejette proprement (InvalidExternalSignal) si un champ obligatoire
        manque ou a un type incorrect. Ne complete JAMAIS une valeur
        manquante par une valeur inventee (pas de confiance par defaut, pas
        de signal par defaut).
        """
        missing = [f for f in REQUIRED_FIELDS if f not in payload or payload[f] is None]
        if missing:
            raise InvalidExternalSignal(
                f"champs obligatoires manquants ou nuls: {missing} (payload recu: "
                f"{sorted(payload.keys())})"
            )
        try:
            confidence = float(payload["confidence"])
        except (TypeError, ValueError) as exc:
            raise InvalidExternalSignal(
                f"confidence invalide (attendu un nombre): {payload['confidence']!r}"
            ) from exc
        source_id = str(payload["source_id"])
        organization_id = str(payload["organization_id"])
        signal = str(payload["signal"])
        rationale = str(payload["rationale"])
        if not source_id or not organization_id or not signal or not rationale:
            raise InvalidExternalSignal(
                "champs obligatoires presents mais vides: source_id/organization_id/"
                "signal/rationale ne peuvent pas etre des chaines vides"
            )
        return cls(
            source_id=source_id,
            organization_id=organization_id,
            signal=signal,
            confidence=confidence,
            rationale=rationale,
            category=str(payload.get("category", "EXTERNAL")),
            adapter_id=(str(payload["adapter_id"]) if payload.get("adapter_id") else None),
            original_event_id=(
                str(payload["original_event_id"]) if payload.get("original_event_id") else None
            ),
            observed_at=(
                float(payload["observed_at"]) if payload.get("observed_at") is not None else None
            ),
            unknowns=tuple(payload.get("unknowns", ())),
            contradictions=tuple(payload.get("contradictions", ())),
            risk_flags=tuple(payload.get("risk_flags", ())),
            evidence_refs=tuple(payload.get("evidence_refs", ())),
            raw_payload=dict(payload),
        )
