"""
Obsidia Trading — port contexte / news (chantier §19).

Une news ne declenche jamais un trade. Elle entre dans le domaine comme une
information parmi d'autres, conserve sa provenance, et alimente les agents de
contexte.

Ce port existe des PASS 2 alors qu'aucune source reelle n'est branchee :
c'est ce qui permettra de brancher la News API Alpaca en PASS 3 sans toucher
au moteur. Les agents de contexte du prototype (Sentiment, Event, Macro)
consomment aujourd'hui des proxies derives du prix — ils deviendront
reellement independants une fois ce port implemente.
"""
from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from domain.market import NewsItem


@runtime_checkable
class NewsPort(Protocol):
    """Acces au contexte editorial / evenementiel."""

    def latest(self, symbols: Sequence[str], limit: int = 20) -> Sequence[NewsItem]:
        """
        Elements de contexte les plus recents pour les symboles demandes.

        Retourne une sequence vide si la source ne repond pas : l'absence de
        contexte est un etat legitime, elle ne doit pas interrompre le cycle.
        """
        ...
