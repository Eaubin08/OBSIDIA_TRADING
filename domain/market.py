"""
Obsidia Trading — representation canonique du marche.

Les structures Alpaca (ou Binance, ou tout autre feed) ne doivent jamais
remonter telles quelles dans le Kernel (chantier §5/§13). Un adapter traduit
la reponse du fournisseur vers ces types ; le reste du systeme ne connait
qu'eux.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from domain.types import AssetClass, DataQuality, Provenance


@dataclass(frozen=True)
class Bar:
    """Chandelle OHLCV normalisee."""

    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def range_pct(self) -> Optional[float]:
        if self.close <= 0:
            return None
        return (self.high - self.low) / self.close


@dataclass(frozen=True)
class Quote:
    """
    Meilleure limite disponible (L1).

    Note d'integration : Alpaca expose le L1 (bid/ask + tailles) mais pas la
    profondeur L2 que le prototype Binance consommait via /depth. Les champs
    de taille restent optionnels pour que l'absence soit visible plutot que
    comblee par une valeur inventee.
    """

    timestamp: float
    bid_price: Optional[float] = None
    ask_price: Optional[float] = None
    bid_size: Optional[float] = None
    ask_size: Optional[float] = None

    @property
    def mid(self) -> Optional[float]:
        if self.bid_price is None or self.ask_price is None:
            return None
        return (self.bid_price + self.ask_price) / 2.0

    @property
    def spread_bps(self) -> Optional[float]:
        mid = self.mid
        if mid is None or mid <= 0:
            return None
        return (self.ask_price - self.bid_price) / mid * 10_000.0

    @property
    def order_book_imbalance(self) -> Optional[float]:
        """
        Desequilibre L1 dans [-1, 1]. None si le fournisseur ne donne pas les
        tailles : le systeme doit pouvoir constater l'absence de la mesure.
        """
        if self.bid_size is None or self.ask_size is None:
            return None
        total = self.bid_size + self.ask_size
        if total <= 0:
            return None
        return (self.bid_size - self.ask_size) / total


@dataclass(frozen=True)
class MarketSnapshot:
    """
    Etat observe d'un instrument a un instant donne.

    `last_price` est la seule donnee reellement obligatoire ; tout le reste est
    optionnel et son absence est portee par la provenance.
    """

    symbol: str
    asset_class: AssetClass
    last_price: float
    provenance: Provenance
    quote: Optional[Quote] = None
    previous_close: Optional[float] = None
    session_high: Optional[float] = None
    session_low: Optional[float] = None
    volume: Optional[float] = None
    bars: Tuple[Bar, ...] = field(default_factory=tuple)
    tradable: bool = True
    market_open: Optional[bool] = None

    @property
    def change_pct(self) -> Optional[float]:
        if self.previous_close is None or self.previous_close <= 0:
            return None
        return (self.last_price - self.previous_close) / self.previous_close

    @property
    def spread_bps(self) -> Optional[float]:
        return self.quote.spread_bps if self.quote else None

    @property
    def is_actionable(self) -> bool:
        """
        Vrai si l'instrument peut porter une action irreversible :
        negociable, marche ouvert (quand l'information existe), prix credible
        et donnee de qualite suffisante.
        """
        if not self.tradable or self.last_price <= 0:
            return False
        if self.market_open is False:
            return False
        return self.provenance.quality.is_trustworthy_for_irreversible_action

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "asset_class": self.asset_class.value,
            "last_price": self.last_price,
            "previous_close": self.previous_close,
            "change_pct": self.change_pct,
            "volume": self.volume,
            "spread_bps": self.spread_bps,
            "order_book_imbalance": (
                self.quote.order_book_imbalance if self.quote else None
            ),
            "tradable": self.tradable,
            "market_open": self.market_open,
            "bars": len(self.bars),
            "provenance": self.provenance.as_dict(),
        }


@dataclass(frozen=True)
class NewsItem:
    """
    Element de contexte externe normalise (chantier §19).

    Une news ne declenche jamais un trade : elle devient une information du
    domaine, consommee par les agents de contexte au meme titre que le reste.
    """

    id: str
    timestamp: float
    headline: str
    symbols: Tuple[str, ...]
    source: str
    summary: str = ""
    url: str = ""

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "headline": self.headline,
            "symbols": list(self.symbols),
            "source": self.source,
            "url": self.url,
        }


@dataclass(frozen=True)
class MarketContext:
    """Contexte de marche partage par le cycle, hors instrument precis."""

    provenance: Provenance
    clock_is_open: Optional[bool] = None
    next_open: Optional[float] = None
    next_close: Optional[float] = None
    news: Tuple[NewsItem, ...] = field(default_factory=tuple)

    def news_for(self, symbol: str) -> Tuple[NewsItem, ...]:
        return tuple(n for n in self.news if symbol in n.symbols)

    def as_dict(self) -> dict:
        return {
            "clock_is_open": self.clock_is_open,
            "next_open": self.next_open,
            "next_close": self.next_close,
            "news_count": len(self.news),
            "provenance": self.provenance.as_dict(),
        }
