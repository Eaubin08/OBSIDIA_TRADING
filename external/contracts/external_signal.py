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

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

REQUIRED_FIELDS = ("source_id", "organization_id", "symbol", "signal", "confidence", "rationale")

# F15 : politique de fraicheur explicite. Aucune donnee empirique ne justifie
# une duree precise pour un signal Trading externe generique — ce nombre est
# un placeholder de securite documente, pas une valeur calibree. Un futur
# adapter concret (ou l'appelant) peut le surcharger via `max_age_seconds`.
DEFAULT_MAX_SIGNAL_AGE_SECONDS = 900.0

# F15 : sentinelle explicite pour "aucune metadonnee de calibration externe
# fournie" — jamais une calibration fabriquee, jamais un champ silencieusement
# absent sans que ce soit tracable dans l'evidence.
NO_EXTERNAL_CALIBRATION_INFORMATION = "NO_EXTERNAL_CALIBRATION_INFORMATION"


class InvalidExternalSignal(ValueError):
    """
    Un payload externe ne porte pas les champs minimums requis, ou porte un
    champ malforme.

    Leve explicitement plutot que de deviner une valeur manquante (chantier
    §30, deja applique a `domain.types.Provenance` et
    `domain.provenance.SourceProvenance`) : une confiance, un symbole ou un
    signal absent ne doit JAMAIS etre invente.
    """


@dataclass(frozen=True)
class ExternalCalibrationMetadata:
    """
    Metadonnees de calibration d'UNE stack externe (F15).

    Le CalibrationPack Native (domain/calibration.py, F13) n'est JAMAIS
    impose a une stack externe : elle peut fournir sa PROPRE calibration,
    sous cette forme, ou n'en fournir aucune (auquel cas
    `external_calibration_id` vaut `NO_EXTERNAL_CALIBRATION_INFORMATION` et
    aucun champ n'est invente en remplacement).
    """

    external_calibration_id: str = NO_EXTERNAL_CALIBRATION_INFORMATION
    dataset_reference: Optional[str] = None
    calibration_version: Optional[str] = None
    created_at: Optional[float] = None
    valid_until: Optional[float] = None
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_present(self) -> bool:
        return self.external_calibration_id != NO_EXTERNAL_CALIBRATION_INFORMATION

    def staleness_status(self, *, now: Optional[float] = None) -> str:
        """
        "UNKNOWN" si aucune calibration n'est fournie ou si `valid_until`
        n'est pas renseigne (on ne devine jamais une duree de validite).
        "STALE" si `now > valid_until`. "FRESH" sinon.
        """
        if not self.is_present or self.valid_until is None:
            return "UNKNOWN"
        current = time.time() if now is None else now
        return "STALE" if current > self.valid_until else "FRESH"


@dataclass(frozen=True)
class ExternalSignal:
    """
    Signal brut, deja valide, en provenance d'une stack externe.

    `unknowns`/`contradictions`/`risk_flags` sont optionnels : si la stack
    externe ne les fournit pas, ils restent des tuples vides. C'est une
    limite documentee (pas une garantie) — un tuple vide signifie ici
    "non rapporte par la source", PAS "verifie comme absent". Voir
    docs/MIGRATION_PROVENANCE.md, section F8, pour la distinction.

    F15 ajoute `symbol` (obligatoire — sans lui, aucune verification de
    coherence marche n'est possible), `strategy_id` (optionnel, distinct de
    `source_id` : une meme source peut heberger plusieurs strategies), et
    `calibration` (F15, jamais la calibration Native).
    """

    source_id: str
    organization_id: str
    symbol: str
    signal: str
    confidence: float
    rationale: str
    category: str = "EXTERNAL"
    strategy_id: Optional[str] = None
    adapter_id: Optional[str] = None
    original_event_id: Optional[str] = None
    observed_at: Optional[float] = None
    unknowns: Tuple[str, ...] = field(default_factory=tuple)
    contradictions: Tuple[str, ...] = field(default_factory=tuple)
    risk_flags: Tuple[str, ...] = field(default_factory=tuple)
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)
    calibration: ExternalCalibrationMetadata = field(default_factory=ExternalCalibrationMetadata)
    raw_payload: Dict[str, Any] = field(default_factory=dict)

    def staleness_status(
        self, *, now: Optional[float] = None, max_age_seconds: float = DEFAULT_MAX_SIGNAL_AGE_SECONDS
    ) -> str:
        """
        "UNKNOWN" si `observed_at` n'est pas fourni (la source ne dit pas
        quand elle a observe ceci — on ne devine jamais). "STALE" si l'age
        depasse `max_age_seconds`. "FRESH" sinon.
        """
        if self.observed_at is None:
            return "UNKNOWN"
        current = time.time() if now is None else now
        return "STALE" if (current - self.observed_at) > max_age_seconds else "FRESH"

    @classmethod
    def from_raw_payload(
        cls, payload: Dict[str, Any], *, expected_symbol: Optional[str] = None
    ) -> "ExternalSignal":
        """
        Etape de VALIDATION du diagramme F8/F15.

        Rejette proprement (InvalidExternalSignal) si un champ obligatoire
        manque, a un type incorrect, ou si `symbol` ne correspond pas a
        `expected_symbol` (quand fourni par l'appelant — ex: le cycle qui
        interroge la stack externe pour un symbole precis). Ne complete
        JAMAIS une valeur manquante par une valeur inventee (pas de
        confiance par defaut, pas de signal par defaut, pas de symbole par
        defaut).
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
        symbol = str(payload["symbol"])
        signal = str(payload["signal"])
        rationale = str(payload["rationale"])
        if not source_id or not organization_id or not symbol or not signal or not rationale:
            raise InvalidExternalSignal(
                "champs obligatoires presents mais vides: source_id/organization_id/"
                "symbol/signal/rationale ne peuvent pas etre des chaines vides"
            )
        if expected_symbol is not None and symbol != expected_symbol:
            raise InvalidExternalSignal(
                f"symbol mismatch: signal externe pour {symbol!r}, "
                f"attendu {expected_symbol!r} — refuse, jamais utilise silencieusement"
            )
        raw_risk_flags = payload.get("risk_flags", ())
        if not isinstance(raw_risk_flags, (list, tuple)) or not all(
            isinstance(item, str) for item in raw_risk_flags
        ):
            raise InvalidExternalSignal(
                f"risk_flags malforme (attendu une liste/tuple de chaines): {raw_risk_flags!r}"
            )
        calibration_payload = payload.get("calibration")
        if calibration_payload:
            calibration = ExternalCalibrationMetadata(
                external_calibration_id=str(
                    calibration_payload.get("external_calibration_id")
                    or NO_EXTERNAL_CALIBRATION_INFORMATION
                ),
                dataset_reference=calibration_payload.get("dataset_reference"),
                calibration_version=calibration_payload.get("calibration_version"),
                created_at=calibration_payload.get("created_at"),
                valid_until=calibration_payload.get("valid_until"),
                evidence_refs=tuple(calibration_payload.get("evidence_refs", ())),
            )
        else:
            calibration = ExternalCalibrationMetadata()
        return cls(
            source_id=source_id,
            organization_id=organization_id,
            symbol=symbol,
            signal=signal,
            confidence=confidence,
            rationale=rationale,
            category=str(payload.get("category", "EXTERNAL")),
            strategy_id=(str(payload["strategy_id"]) if payload.get("strategy_id") else None),
            adapter_id=(str(payload["adapter_id"]) if payload.get("adapter_id") else None),
            original_event_id=(
                str(payload["original_event_id"]) if payload.get("original_event_id") else None
            ),
            observed_at=(
                float(payload["observed_at"]) if payload.get("observed_at") is not None else None
            ),
            unknowns=tuple(payload.get("unknowns", ())),
            contradictions=tuple(payload.get("contradictions", ())),
            risk_flags=tuple(raw_risk_flags),
            evidence_refs=tuple(payload.get("evidence_refs", ())),
            calibration=calibration,
            raw_payload=dict(payload),
        )
