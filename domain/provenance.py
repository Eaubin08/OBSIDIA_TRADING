"""
Obsidia Trading — SourceProvenance (chantier F7.5, Source Provenance Closure).

Ne pas confondre avec `domain.types.Provenance` : celle-ci decrit la
FRAICHEUR/QUALITE d'une donnee de marche (LIVE/DELAYED/CACHED/SYNTHETIC/
STALE/MISSING, cf. domain/types.py::DataQuality). `SourceProvenance` decrit
autre chose : D'OU VIENT UN SIGNAL (agent natif, stack externe, operateur
humain, replay, simulation) — une question orthogonale a la fraicheur de la
donnee de marche sous-jacente. Les deux peuvent coexister sur le meme cycle
sans se substituer l'une a l'autre.

REGLE CENTRALE (verifiee par tests/unit/test_source_provenance.py) :

    La provenance decrit D'OU VIENT l'information. Elle ne donne AUCUNE
    autorite supplementaire ni inferieure.

    source_system=EXTERNAL  n'est PAS moins fiable par construction.
    source_system=NATIVE    n'est PAS plus fiable par construction.
    source_system=HUMAN     n'est PAS la verite par construction.

    C'est de l'evidence contextuelle, jamais une decision. Rien dans ce
    module ne doit jamais influencer `Decision.authority` — voir
    `governance/bridge/governance_bridge.py`, qui ne lit jamais ce champ.

Integration (F7.5) :

    Source -> AgentOutput / ExternalSignal -> Canonical Contract
           -> Governance Bridge -> Receipt

`SourceProvenance` est attachee a `domain.proposal.AgentOutput.source_provenance`
et traverse jusqu'au receipt sans transformation, exactement comme
`unknowns`/`contradictions`/`risk_flags` depuis F3.5 : le Governance Bridge
(F5) transmet `proposal` (donc `agent_outputs`, donc leur provenance) sans
jamais la lire ni la modifier.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class SourceSystem(str, Enum):
    """D'ou vient le signal, au sens large."""

    NATIVE = "native"
    EXTERNAL = "external"
    HUMAN = "human"
    REPLAY = "replay"
    SIMULATION = "simulation"


class SourceKind(str, Enum):
    """Quel genre de chose a produit le signal, independamment du systeme."""

    AGENT = "agent"
    MODEL = "model"
    RULE = "rule"
    OPERATOR = "operator"
    API = "api"
    ADAPTER = "adapter"
    DATASET = "dataset"
    SENSOR = "sensor"


@dataclass(frozen=True)
class SourceProvenance:
    """
    Provenance stable et extensible d'un signal, jusqu'au receipt.

    Champs optionnels a None plutot qu'a une valeur inventee : chantier §30
    (deja applique a `domain.types.Provenance`) — ce qui n'est pas connu ne
    doit jamais etre devine.
    """

    source_system: SourceSystem
    source_kind: SourceKind
    source_id: str
    adapter_id: Optional[str] = None
    organization_id: Optional[str] = None
    original_event_id: Optional[str] = None
    observed_at: Optional[float] = None
    ingested_at: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source_system": self.source_system.value,
            "source_kind": self.source_kind.value,
            "source_id": self.source_id,
            "adapter_id": self.adapter_id,
            "organization_id": self.organization_id,
            "original_event_id": self.original_event_id,
            "observed_at": self.observed_at,
            "ingested_at": self.ingested_at,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["SourceProvenance"]:
        """
        Reconstruction depuis un dict serialise (JSONL reload, F7).

        Retourne None si `data` est None : un receipt ecrit avant F7.5 n'a
        simplement pas ce champ, ce n'est pas une erreur de lecture (voir
        docs/MIGRATION_PROVENANCE.md, section F7.5, "compatibilite schema").
        """
        if data is None:
            return None
        return cls(
            source_system=SourceSystem(data["source_system"]),
            source_kind=SourceKind(data["source_kind"]),
            source_id=data["source_id"],
            adapter_id=data.get("adapter_id"),
            organization_id=data.get("organization_id"),
            original_event_id=data.get("original_event_id"),
            observed_at=data.get("observed_at"),
            ingested_at=data.get("ingested_at"),
        )

    # ── Constructeurs dedies ────────────────────────────────────────────
    # Objectif : eviter que des valeurs par defaut (source_system=NATIVE,
    # source_kind=AGENT, ...) se dispersent dans tout le code appelant.
    # Un seul endroit sait comment tagger un signal natif ; un seul endroit
    # saura, plus tard, comment tagger un signal externe (F8).

    @classmethod
    def for_native_agent(
        cls,
        agent_id: str,
        *,
        observed_at: Optional[float] = None,
        ingested_at: Optional[float] = None,
    ) -> "SourceProvenance":
        """Provenance automatique d'un agent du roster natif (17 agents, F3)."""
        return cls(
            source_system=SourceSystem.NATIVE,
            source_kind=SourceKind.AGENT,
            source_id=agent_id,
            observed_at=observed_at,
            ingested_at=ingested_at,
        )

    @classmethod
    def for_external_signal(
        cls,
        *,
        source_id: str,
        source_kind: SourceKind,
        adapter_id: str,
        organization_id: Optional[str] = None,
        original_event_id: Optional[str] = None,
        observed_at: Optional[float] = None,
        ingested_at: Optional[float] = None,
    ) -> "SourceProvenance":
        """
        Provenance d'un signal normalise par un adapter externe (F8).

        `source_system` est TOUJOURS EXTERNAL ici — jamais reecrit en NATIVE,
        quelle que soit la confiance accordee au signal par ailleurs.
        """
        return cls(
            source_system=SourceSystem.EXTERNAL,
            source_kind=source_kind,
            source_id=source_id,
            adapter_id=adapter_id,
            organization_id=organization_id,
            original_event_id=original_event_id,
            observed_at=observed_at,
            ingested_at=ingested_at,
        )

    @classmethod
    def for_replay_of(
        cls,
        original: "SourceProvenance",
        *,
        replayed_at: float,
    ) -> "SourceProvenance":
        """
        Provenance d'un signal REGENERE pendant un replay (proof/receipts/replay.py).

        N'est PAS utilisee pour la simple LECTURE d'un receipt existant :
        `replay_audit` renvoie la provenance originale telle quelle (voir
        AuditReplayResult, qui recopie le dict brut stocke sans y toucher).
        Ce constructeur sert au cas ou un futur mecanisme de replay
        regenererait activement un signal (ex: rejouer un agent, pas
        seulement une simulation) : le resultat ne doit alors jamais se
        faire passer pour une nouvelle observation native, meme si la
        source originale l'etait.
        """
        return cls(
            source_system=SourceSystem.REPLAY,
            source_kind=original.source_kind,
            source_id=original.source_id,
            adapter_id=original.adapter_id,
            organization_id=original.organization_id,
            original_event_id=original.original_event_id or original.source_id,
            observed_at=original.observed_at,
            ingested_at=replayed_at,
        )
