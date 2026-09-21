"""
Obsidia Trading — Normalizer (chantier F8, External Stack Adapter).

Traduit `ExternalSignal` (external/contracts/external_signal.py) vers le
contrat canonique (`domain.contracts.canonical.to_canonical_agent_signal`,
F3.5) — LE MEME point de convergence que le chemin natif
(`native/agents/adapter.py`). Aucun second chemin de gouvernance n'existe :
apres ce module, un signal externe est indiscernable structurellement d'un
signal natif pour Sigma/Guard/KX108 — seule sa `source_provenance` differe.

REGLES NON NEGOCIABLES (verifiees par tests/unit/test_external_adapter.py) :
    Adapter != Agent Authority — ce module ne vote pas, ne juge jamais un
        signal ; il traduit ce que la stack externe a deja produit.
    Adapter != Governance — aucun import de governance/bridge/ ici ; ce
        module produit un AgentOutput, exactement comme le chemin natif,
        et le soumet au meme pipeline sans jamais y toucher.
    Adapter != KX108 — ne produit jamais de verdict.
    Adapter != Binder / Execution — aucun import execution.binder ni
        market.adapters.alpaca.
"""
from __future__ import annotations

from domain.contracts.canonical import CanonicalAgentSignal, to_canonical_agent_signal
from domain.provenance import SourceKind, SourceProvenance
from external.contracts.external_signal import ExternalSignal


def normalize_external_signal(
    signal: ExternalSignal,
    *,
    adapter_id: str,
    source_kind: SourceKind = SourceKind.API,
) -> CanonicalAgentSignal:
    """
    Etapes NORMALIZATION + PROVENANCE PRESERVATION du diagramme F8.

    `adapter_id` est fourni par l'appelant (l'adapter concret sait qui il
    est) plutot que lu depuis `signal.adapter_id`, qui peut etre absent ou
    different : cela garantit qu'un signal ne peut jamais se faire passer
    pour "sans adapter" en omettant le champ. `source_provenance.source_id`
    reste TOUJOURS celui d'origine (`signal.source_id`), jamais reecrit en
    l'identifiant de l'adapter.

    Ne fait AUCUNE inference : `unknowns`/`contradictions`/`risk_flags`
    absents du signal externe restent des tuples vides — voir
    `ExternalSignal`, ils ne sont ni inventes ni reinterpretes comme "risque
    verifie absent".
    """
    provenance = SourceProvenance.for_external_signal(
        source_id=signal.source_id,
        source_kind=source_kind,
        adapter_id=adapter_id,
        organization_id=signal.organization_id,
        original_event_id=signal.original_event_id,
        observed_at=signal.observed_at,
    )
    return to_canonical_agent_signal(
        agent_id=signal.source_id,
        category=signal.category,
        signal=signal.signal,
        confidence=signal.confidence,
        rationale=signal.rationale,
        unknowns=signal.unknowns,
        contradictions=signal.contradictions,
        risk_flags=signal.risk_flags,
        evidence_refs=signal.evidence_refs,
        operational_metadata={"raw_payload_keys": sorted(signal.raw_payload.keys())},
        source_provenance=provenance,
    )
