"""
Obsidia Trading — contrats internes du moteur.

Les ports (obsidia/ports/) decrivent ce qui sort du systeme vers le monde.
Ces contrats-ci decrivent les etapes cognitives internes du cycle. Les
separer permet de remplacer une etape — un jeu d'agents, une politique de
sizing, une autorite — sans toucher a l'orchestration.

Rappel du chantier §12 : aucune de ces etapes n'a d'autorite, sauf
AuthorityPort. Les autres observent, analysent, envisagent et dimensionnent.
"""
from __future__ import annotations

from typing import Optional, Protocol, Sequence, runtime_checkable

from domain.market import MarketSnapshot
from domain.portfolio import PortfolioState
from domain.proposal import (
    ActionProposal,
    AgentOutput,
    Consensus,
    Opportunity,
    SizingDecision,
    StrategyCandidate,
)
from domain.receipt import Decision
from domain.state import TradingDomainState


@runtime_checkable
class DiscoveryPort(Protocol):
    """
    Decouverte d'opportunites (chantier §6).

    Repond a « qu'est-ce qui merite mon attention maintenant », et non a
    « que penser de ce symbole precis ». Couvre aussi bien les entrees
    potentielles que les positions existantes a surveiller.
    """

    def discover(self, state: TradingDomainState) -> Sequence[Opportunity]:
        ...


@runtime_checkable
class AnalysisPort(Protocol):
    """
    Analyse d'un instrument par un ensemble d'agents.

    C'est ici que vivent les 14 agents deterministes du prototype. Ils
    produisent des signaux, jamais des ordres.
    """

    def analyse(
        self,
        symbol: str,
        snapshot: MarketSnapshot,
        portfolio: Optional[PortfolioState],
    ) -> Sequence[AgentOutput]:
        ...


@runtime_checkable
class AggregationPort(Protocol):
    """Reduction d'un ensemble de signaux en un consensus."""

    def aggregate(self, outputs: Sequence[AgentOutput]) -> Consensus:
        ...


@runtime_checkable
class StrategyPort(Protocol):
    """
    Construction des manieres concretes de repondre (chantier §9).

    Peut retourner plusieurs candidates pour un meme symbole : c'est ce qui
    rend la comparaison possible. Une liste vide est une reponse valide.
    """

    def build(
        self,
        symbol: str,
        snapshot: MarketSnapshot,
        consensus: Consensus,
        portfolio: Optional[PortfolioState],
        opportunities: Sequence[Opportunity] = (),
    ) -> Sequence[StrategyCandidate]:
        ...


@runtime_checkable
class SizingPort(Protocol):
    """
    Dimensionnement (chantier §11).

    Volontairement separe de la direction : le systeme doit pouvoir reduire
    ou refuser une taille sans changer d'avis sur le sens de l'operation.
    """

    def size(
        self,
        candidate: StrategyCandidate,
        snapshot: MarketSnapshot,
        portfolio: Optional[PortfolioState],
    ) -> SizingDecision:
        ...


@runtime_checkable
class AuthorityPort(Protocol):
    """
    X-108 (chantier §12).

    Seule etape du cycle habilitee a produire une autorite. Elle recoit une
    proposition complete et l'etat du domaine, et repond ACT, HOLD ou BLOCK.
    """

    def evaluate(
        self,
        proposal: ActionProposal,
        state: TradingDomainState,
        decision_id: str,
    ) -> Decision:
        ...


@runtime_checkable
class PlannerPort(Protocol):
    """
    Traduction d'une decision autorisee en ordre broker (chantier §14).

    Retourne None quand la decision n'appelle aucun ordre — ce qui est le cas
    de tout verdict autre que ACT, et aussi d'un ACT portant une action non
    irreversible.
    """

    def plan(self, decision: Decision, state: TradingDomainState):
        ...
