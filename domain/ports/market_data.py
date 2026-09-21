"""
Obsidia Trading — port donnees de marche.

Le moteur demande un instantane du monde ; il ignore si celui-ci vient
d'Alpaca, de Binance ou d'un mock. C'est la frontiere posee par le chantier
§13 : le Kernel n'appelle jamais un broker directement.

Contrat de degradation (chantier §30) : une implementation ne doit JAMAIS
inventer une valeur manquante. Si un prix est indisponible, elle leve
MarketDataUnavailable ou retourne un instantane dont la provenance porte
DataQuality.MISSING / STALE. Un silence est une faute.
"""
from __future__ import annotations

from typing import Optional, Protocol, Sequence, runtime_checkable

from domain.market import Bar, MarketContext, MarketSnapshot


class MarketDataUnavailable(RuntimeError):
    """Le feed ne peut pas repondre. L'appelant doit degrader explicitement."""


@runtime_checkable
class MarketDataPort(Protocol):
    """Acces en lecture au marche."""

    def snapshot(self, symbol: str) -> MarketSnapshot:
        """
        Instantane courant d'un instrument.

        Leve MarketDataUnavailable si l'instrument est inconnu ou le feed
        injoignable.
        """
        ...

    def snapshots(self, symbols: Sequence[str]) -> dict[str, MarketSnapshot]:
        """
        Instantanes de plusieurs instruments.

        Les symboles indisponibles sont absents du resultat : leur absence
        doit rester visible, et non comblee.
        """
        ...

    def history(self, symbol: str, limit: int = 200) -> Sequence[Bar]:
        """Historique de chandelles, du plus ancien au plus recent."""
        ...

    def context(self) -> Optional[MarketContext]:
        """Contexte de marche global (horaires, news), si le feed en fournit."""
        ...
