"""Adaptation Alpaca market data vers MarketDataPort."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence

from market.adapters.alpaca.legacy_indicators import MarketState
from domain.market import Bar, MarketContext, MarketSnapshot, NewsItem, Quote
from domain.types import AssetClass, DataQuality, Mode, Provenance
from domain.ports.clock import ClockPort, SystemClock
from domain.ports.market_data import MarketDataUnavailable
from market.adapters.alpaca.alpaca_client import AlpacaAPIError, AlpacaHTTPClient, market_unavailable


class AlpacaMarketDataProvider:
    """MarketDataPort backed by Alpaca data endpoints."""

    def __init__(
        self,
        client: AlpacaHTTPClient,
        *,
        mode: Optional[Mode] = None,
        clock: Optional[ClockPort] = None,
        asset_classes: Optional[Dict[str, AssetClass]] = None,
        news_provider: Optional[Any] = None,
    ) -> None:
        self.client = client
        self.mode = mode or client.config.mode
        self.clock: ClockPort = clock or SystemClock()
        self.asset_classes = dict(asset_classes or {})
        self.news_provider = news_provider
        self._market_states: Dict[str, MarketState] = {}

    def snapshot(self, symbol: str) -> MarketSnapshot:
        asset_class = self.asset_classes.get(symbol, self._infer_asset_class(symbol))
        try:
            trade = self._latest_trade(symbol, asset_class)
            quote = self._latest_quote(symbol, asset_class)
            bars = tuple(self.history(symbol, limit=2))
        except AlpacaAPIError as exc:
            raise market_unavailable(exc) from exc

        price = _number(trade, "p", "price")
        if price is None or price <= 0:
            raise MarketDataUnavailable(f"prix Alpaca indisponible pour {symbol}")

        provenance = Provenance(
            source="alpaca",
            fetched_at=self.clock.now(),
            quality=DataQuality.LIVE,
            mode=self.mode,
            degraded_reasons=(),
        )

        previous_close = bars[-2].close if len(bars) >= 2 else None
        latest_bar = bars[-1] if bars else None
        quote_obj = self._quote_from(quote)
        if quote_obj is None:
            provenance = provenance.degraded(
                "quote L1 indisponible", DataQuality.DELAYED
            )

        return MarketSnapshot(
            symbol=symbol,
            asset_class=asset_class,
            last_price=price,
            provenance=provenance,
            quote=quote_obj,
            previous_close=previous_close,
            session_high=latest_bar.high if latest_bar else None,
            session_low=latest_bar.low if latest_bar else None,
            volume=latest_bar.volume if latest_bar else None,
            bars=bars,
            tradable=True,
            market_open=None,
        )

    def snapshots(self, symbols: Sequence[str]) -> Dict[str, MarketSnapshot]:
        out: Dict[str, MarketSnapshot] = {}
        for symbol in symbols:
            try:
                out[symbol] = self.snapshot(symbol)
            except MarketDataUnavailable:
                continue
        return out

    def history(self, symbol: str, limit: int = 200) -> Sequence[Bar]:
        asset_class = self.asset_classes.get(symbol, self._infer_asset_class(symbol))
        try:
            if asset_class is AssetClass.CRYPTO:
                data = self.client.data_get(
                    f"/v1beta3/crypto/{self.client.config.crypto_location}/bars",
                    params={
                        "symbols": symbol,
                        "timeframe": "1Min",
                        "limit": limit,
                    },
                )
                raw_bars = (data.get("bars") or {}).get(symbol) or []
            else:
                data = self.client.data_get(
                    f"/v2/stocks/{symbol}/bars",
                    params={
                        "timeframe": "1Min",
                        "limit": limit,
                        "feed": self.client.config.data_feed,
                    },
                )
                raw_bars = data.get("bars") or []
        except AlpacaAPIError as exc:
            raise market_unavailable(exc) from exc

        bars = []
        for item in raw_bars:
            bar = self._bar_from(item)
            if bar is not None:
                bars.append(bar)
        return tuple(bars)

    def market_state(self, symbol: str) -> Optional[MarketState]:
        """
        Pont vers les agents historiques.

        PASS 3 ne reecrit pas la cognition : les 14 agents consomment encore
        `MarketState`. On l'hydrate depuis les bars Alpaca sans inventer de
        news ; sentiment et event risk restent neutres tant que NewsPort n'est
        pas relie aux agents de contexte.
        """
        if symbol in self._market_states:
            return self._market_states[symbol]

        bars = self.history(symbol, limit=200)
        if not bars:
            return None
        state = MarketState(symbol=symbol)
        for bar in bars:
            spread_bps = 0.0
            imbalance = 0.0
            state.update(
                price=bar.close,
                high=bar.high,
                low=bar.low,
                volume=bar.volume,
                spread_bps=spread_bps,
                order_book_imbalance=imbalance,
                sentiment_score=0.0,
                event_risk=0.0,
                btc_reference_price=bar.close,
            )
        self._market_states[symbol] = state
        return state

    def context(self) -> Optional[MarketContext]:
        news: Sequence[NewsItem] = ()
        if self.news_provider is not None:
            try:
                news = self.news_provider.latest((), limit=20)
            except Exception:  # noqa: BLE001 - context is optional
                news = ()
        return MarketContext(
            provenance=Provenance(
                source="alpaca",
                fetched_at=self.clock.now(),
                quality=DataQuality.LIVE if news else DataQuality.MISSING,
                mode=self.mode,
                degraded_reasons=() if news else ("news Alpaca non chargees",),
            ),
            clock_is_open=None,
            news=tuple(news),
        )

    def _latest_trade(self, symbol: str, asset_class: AssetClass) -> dict[str, Any]:
        if asset_class is AssetClass.CRYPTO:
            data = self.client.data_get(
                f"/v1beta3/crypto/{self.client.config.crypto_location}/latest/trades",
                params={"symbols": symbol},
            )
            return (data.get("trades") or {}).get(symbol) or {}
        data = self.client.data_get(
            f"/v2/stocks/{symbol}/trades/latest",
            params={"feed": self.client.config.data_feed},
        )
        return data.get("trade") or {}

    def _latest_quote(self, symbol: str, asset_class: AssetClass) -> dict[str, Any]:
        if asset_class is AssetClass.CRYPTO:
            data = self.client.data_get(
                f"/v1beta3/crypto/{self.client.config.crypto_location}/latest/quotes",
                params={"symbols": symbol},
            )
            return (data.get("quotes") or {}).get(symbol) or {}
        data = self.client.data_get(
            f"/v2/stocks/{symbol}/quotes/latest",
            params={"feed": self.client.config.data_feed},
        )
        return data.get("quote") or {}

    def _quote_from(self, payload: dict[str, Any]) -> Optional[Quote]:
        bid = _number(payload, "bp", "bid_price")
        ask = _number(payload, "ap", "ask_price")
        if bid is None and ask is None:
            return None
        return Quote(
            timestamp=_timestamp(payload.get("t")) or self.clock.now(),
            bid_price=bid,
            ask_price=ask,
            bid_size=_number(payload, "bs", "bid_size"),
            ask_size=_number(payload, "as", "ask_size"),
        )

    def _bar_from(self, payload: dict[str, Any]) -> Optional[Bar]:
        close = _number(payload, "c", "close")
        if close is None:
            return None
        return Bar(
            timestamp=_timestamp(payload.get("t")) or self.clock.now(),
            open=_number(payload, "o", "open") or close,
            high=_number(payload, "h", "high") or close,
            low=_number(payload, "l", "low") or close,
            close=close,
            volume=_number(payload, "v", "volume") or 0.0,
        )

    @staticmethod
    def _infer_asset_class(symbol: str) -> AssetClass:
        return AssetClass.CRYPTO if "/" in symbol else AssetClass.EQUITY


def _number(payload: dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        value = payload.get(key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _timestamp(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw).astimezone(timezone.utc).timestamp()
    except ValueError:
        return None
