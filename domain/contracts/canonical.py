"""
Canonical Domain Contract (F3.5).

Ce module ne redefinit PAS de nouveaux types de donnees paralleles a ceux
deja portes dans domain/*.py — Obsidia Trading a deja un socle de types
immuables solide (herite d'agent-trad-main) qui couvre exactement ce que le
contrat canonique demande. Dupliquer ces dataclasses creerait deux sources
de verite pour la meme notion, ce qui est exactement le risque que ce
document sert a fermer.

Ce module fait deux choses :

1. Nomme explicitement, pour un lecteur qui ne connait pas l'historique du
   code, OU vit chaque concept demande par le contrat canonique.
2. Fournit un point de convergence unique et documente
   (`to_canonical_agent_signal`) par lequel TOUT producteur de signal
   d'agent — natif (native/agents/adapter.py) ou externe
   (external/normalization/, futur) — doit passer pour entrer dans le
   pipeline de gouvernance. Aucun second chemin ne doit exister.

## Table de correspondance (vocabulaire demande -> type reel)

| Concept canonique      | Type reel                                  | Fichier                        |
|-------------------------|---------------------------------------------|---------------------------------|
| MarketState              | `MarketSnapshot`                            | domain/market.py                |
| TradingDomainState       | `TradingDomainState`                        | domain/state.py                 |
| TradeProposal            | `Opportunity` + `StrategyCandidate`         | domain/proposal.py              |
| TradeIntent              | `ActionProposal` (ce qui est soumis a X-108)| domain/proposal.py              |
| AgentVote                | `AgentOutput` (alias `CanonicalAgentSignal`)| domain/proposal.py              |
| Evidence                 | `AgentOutput.evidence_refs`                 | domain/proposal.py              |
| Confidence               | `AgentOutput.confidence` / `Consensus.confidence` | domain/proposal.py        |
| RiskFlags                | `AgentOutput.risk_flags`                    | domain/proposal.py              |
| Unknowns                 | `AgentOutput.unknowns`                      | domain/proposal.py              |
| Contradictions           | `AgentOutput.contradictions`                | domain/proposal.py              |
| Provenance (fraicheur donnee marche) | `Provenance`                    | domain/types.py                 |
| Provenance (origine du signal, F7.5) | `SourceProvenance` (`AgentOutput.source_provenance`) | domain/provenance.py |
| Contexte temporel        | `Provenance.fetched_at` / `TradingDomainState.observed_at` | domain/types.py, domain/state.py |
| Contexte portfolio       | `PortfolioState` / `ActionProposal.portfolio_context` | domain/portfolio.py, domain/proposal.py |
| Contraintes d'execution  | `SizingDecision.capped_by` / `ExecutionPlan` | domain/proposal.py, domain/orders.py |
| Decision X-108           | `Decision`                                  | domain/receipt.py               |
| Preuve                   | `CycleReceipt`                              | domain/receipt.py               |

Ces quatre champs (`unknowns`, `contradictions`, `risk_flags`,
`evidence_refs`) sont des champs de PREMIERE CLASSE sur `AgentOutput` depuis
F3.5 — ils ne sont plus compresses dans un blob libre. Voir
tests/unit/test_canonical_contract_integrity.py pour la preuve qu'ils
survivent jusqu'au receipt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence, Tuple

from domain.proposal import ActionProposal, AgentOutput
from domain.provenance import SourceProvenance
from domain.receipt import CycleReceipt, Decision
from domain.state import TradingDomainState

# Alias documentaire : AgentOutput EST la representation canonique d'un
# signal d'agent, natif ou externe. Ne pas creer de second type.
CanonicalAgentSignal = AgentOutput


def to_canonical_agent_signal(
    *,
    agent_id: str,
    category: str,
    signal: str,
    confidence: float,
    rationale: str,
    unknowns: Iterable[str] = (),
    contradictions: Iterable[str] = (),
    risk_flags: Iterable[str] = (),
    evidence_refs: Iterable[str] = (),
    operational_metadata: Optional[dict] = None,
    source_provenance: Optional[SourceProvenance] = None,
) -> CanonicalAgentSignal:
    """
    Point de convergence UNIQUE pour transformer n'importe quelle source de
    signal d'agent (roster natif OU futur adapter externe) en
    CanonicalAgentSignal.

    Regle absolue : `unknowns`, `contradictions` et `risk_flags` ne doivent
    jamais etre resumes, hashes ou tronques ici. Ils traversent tels quels.

    F7.5 : `source_provenance` est optionnel ici (compatibilite historique
    des appelants qui existaient avant F7.5), mais tout appelant natif ou
    externe DEVRAIT le fournir — voir domain/provenance.py::for_native_agent
    et ::for_external_signal.
    """
    return CanonicalAgentSignal(
        name=agent_id,
        category=category,
        signal=signal,
        confidence=float(confidence),
        rationale=rationale,
        unknowns=tuple(unknowns),
        contradictions=tuple(contradictions),
        risk_flags=tuple(risk_flags),
        evidence_refs=tuple(evidence_refs),
        inputs_digest=dict(operational_metadata or {}),
        source_provenance=source_provenance,
    )


@dataclass(frozen=True)
class CanonicalCycleView:
    """
    Vue en lecture seule d'un cycle complet, assemblee pour verification et
    pour l'UI/audit — jamais utilisee pour decider (ce n'est pas une
    autorite, seulement une facon de repondre a « qu'est-ce qui est
    reellement arrive a ce que l'agent a signale ? »).
    """

    state: TradingDomainState
    agent_signals: Tuple[CanonicalAgentSignal, ...] = field(default_factory=tuple)
    proposal: Optional[ActionProposal] = None
    decision: Optional[Decision] = None
    receipt: Optional[CycleReceipt] = None

    def all_unknowns(self) -> Tuple[str, ...]:
        return tuple(u for s in self.agent_signals for u in s.unknowns)

    def all_contradictions(self) -> Tuple[str, ...]:
        return tuple(c for s in self.agent_signals for c in s.contradictions)

    def all_risk_flags(self) -> Tuple[str, ...]:
        return tuple(r for s in self.agent_signals for r in s.risk_flags)

    def receipt_preserves_agent_semantics(self) -> bool:
        """
        Vrai si tout unknown/contradiction/risk_flag produit par un agent de
        ce cycle est bien retrouvable dans le contenu hashable du receipt
        final. Utilise par les tests de non-regression semantique.
        """
        if self.receipt is None:
            return not (
                self.all_unknowns() or self.all_contradictions() or self.all_risk_flags()
            )
        blob = str(self.receipt._hashable_content())  # noqa: SLF001 - lecture de verification uniquement
        return all(
            token in blob
            for token in (*self.all_unknowns(), *self.all_contradictions(), *self.all_risk_flags())
        )
