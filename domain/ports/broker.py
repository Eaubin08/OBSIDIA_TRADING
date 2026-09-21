"""
Obsidia Trading — port broker (chantier §15).

Le bridge d'execution n'a AUCUNE autorite. Il execute une decision deja
autorisee, il ne la prend pas et ne la revise pas.

Deux garanties portees par ce contrat :

  1. Toute methode modifiant l'exterieur recoit un ExecutionPlan, jamais des
     parametres bruts. Le plan porte l'autorite qui l'a permis, donc
     l'implementation peut verifier elle-meme son droit d'agir plutot que de
     faire confiance a son appelant.

  2. Un refus est toujours explicite. Une implementation ne retourne jamais
     silencieusement sans agir — c'est exactement le defaut B4 du prototype,
     ou un achat non finance disparaissait sans laisser de trace.

Le port couvre aussi la lecture (compte, positions, ordres), qui alimente le
monitoring post-execution du chantier §17.
"""
from __future__ import annotations

from typing import Optional, Protocol, Sequence, runtime_checkable

from domain.orders import ExecutionPlan, ExecutionResult
from domain.portfolio import AccountState, Order, PortfolioState, Position


class BrokerUnavailable(RuntimeError):
    """Le broker est injoignable. L'appelant doit degrader explicitement."""


class UnauthorizedExecution(PermissionError):
    """
    Tentative d'executer un plan non porte par Authority.ACT.

    Cette exception ne doit jamais survenir en fonctionnement nominal : le
    moteur ne construit pas de plan sans autorite. Elle existe comme dernier
    verrou, au plus pres de l'action irreversible, pour qu'une erreur de
    cablage echoue bruyamment plutot que de laisser passer un ordre.
    """


@runtime_checkable
class BrokerPort(Protocol):
    """Acces au broker : lecture d'etat et execution de plans autorises."""

    # ── Lecture ──────────────────────────────────────────────────────────

    def account(self) -> AccountState:
        """Etat du compte. Leve BrokerUnavailable si injoignable."""
        ...

    def positions(self) -> Sequence[Position]:
        """Positions ouvertes declarees par le broker."""
        ...

    def open_orders(self) -> Sequence[Order]:
        """Ordres en cours."""
        ...

    def portfolio(self) -> PortfolioState:
        """Vue consolidee compte + positions + ordres."""
        ...

    def order_status(self, broker_order_id: str) -> Optional[Order]:
        """Etat courant d'un ordre, ou None s'il est inconnu du broker."""
        ...

    def order_by_client_order_id(self, client_order_id: str) -> Optional[Order]:
        """Retrouve un ordre par identifiant idempotent cote client."""
        ...

    # ── Ecriture (exige Authority.ACT) ───────────────────────────────────

    def submit(self, plan: ExecutionPlan) -> ExecutionResult:
        """
        Soumet un plan autorise.

        L'implementation DOIT lever UnauthorizedExecution si
        `plan.is_authorized` est faux, avant tout contact avec l'exterieur.
        """
        ...

    def cancel(self, plan: ExecutionPlan, broker_order_id: str) -> ExecutionResult:
        """Annule un ordre en cours. Exige egalement une autorite ACT."""
        ...

    def replace(self, plan: ExecutionPlan, broker_order_id: str) -> ExecutionResult:
        """
        Remplace un ordre en cours.

        Peut lever NotImplementedError si le broker ne le supporte pas pour la
        classe d'actif concernee : une capacite absente doit se constater, pas
        se simuler.
        """
        ...

    def close_position(self, plan: ExecutionPlan) -> ExecutionResult:
        """Ferme une position existante. Exige une autorite ACT."""
        ...
