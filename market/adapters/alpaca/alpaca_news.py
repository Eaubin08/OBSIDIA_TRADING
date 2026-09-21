"""Adaptation Alpaca News API vers NewsPort."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from domain.market import NewsItem
from market.adapters.alpaca.alpaca_client import AlpacaAPIError, AlpacaHTTPClient


class AlpacaNewsProvider:
    """NewsPort backed by Alpaca news endpoint when available."""

    def __init__(self, client: AlpacaHTTPClient) -> None:
        self.client = client

    def latest(self, symbols: Sequence[str], limit: int = 20) -> Sequence[NewsItem]:
        params: dict[str, Any] = {"limit": limit}
        if symbols:
            params["symbols"] = ",".join(symbols)
        try:
            data = self.client.data_get("/v1beta1/news", params=params)
        except AlpacaAPIError:
            return ()
        raw_news = data.get("news") if isinstance(data, dict) else None
        if not isinstance(raw_news, list):
            return ()
        return tuple(self._item_from(item) for item in raw_news[:limit])

    def _item_from(self, payload: dict[str, Any]) -> NewsItem:
        return NewsItem(
            id=str(payload.get("id") or payload.get("url") or ""),
            timestamp=_timestamp(payload.get("created_at") or payload.get("updated_at")) or 0.0,
            headline=str(payload.get("headline") or ""),
            symbols=tuple(payload.get("symbols") or ()),
            source=str(payload.get("source") or "alpaca"),
            summary=str(payload.get("summary") or ""),
            url=str(payload.get("url") or ""),
        )


def _timestamp(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw).astimezone(timezone.utc).timestamp()
    except ValueError:
        return None

