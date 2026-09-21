"""Client HTTP Alpaca minimal avec transport injectable pour tests."""
from __future__ import annotations

from typing import Any, Mapping, Optional

import requests

from domain.ports.broker import BrokerUnavailable
from domain.ports.market_data import MarketDataUnavailable
from market.adapters.alpaca.alpaca_config import AlpacaConfig


class AlpacaAPIError(RuntimeError):
    """Erreur explicite retournee par Alpaca ou par le transport."""


class AlpacaHTTPClient:
    """
    Client HTTP sans dependance SDK dans le domaine.

    Le transport doit exposer une methode `request(...)` compatible requests.
    Les tests injectent un fake transport ; en runtime, une Session requests
    est utilisee.
    """

    def __init__(
        self,
        config: AlpacaConfig,
        *,
        transport: Optional[Any] = None,
    ) -> None:
        self.config = config
        self._transport = transport or requests.Session()

    def trading_get(
        self, path: str, *, params: Optional[Mapping[str, Any]] = None
    ) -> Any:
        return self._request("GET", self.config.trading_base_url, path, params=params)

    def trading_post(self, path: str, *, json_body: Mapping[str, Any]) -> Any:
        return self._request("POST", self.config.trading_base_url, path, json_body=json_body)

    def trading_delete(
        self, path: str, *, json_body: Optional[Mapping[str, Any]] = None
    ) -> Any:
        return self._request("DELETE", self.config.trading_base_url, path, json_body=json_body)

    def data_get(
        self, path: str, *, params: Optional[Mapping[str, Any]] = None
    ) -> Any:
        return self._request("GET", self.config.data_base_url, path, params=params)

    def _request(
        self,
        method: str,
        base_url: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json_body: Optional[Mapping[str, Any]] = None,
    ) -> Any:
        url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
        try:
            response = self._transport.request(
                method,
                url,
                headers=self.config.auth_headers(),
                params=dict(params or {}),
                json=dict(json_body or {}) if json_body is not None else None,
                timeout=self.config.timeout_s,
            )
        except requests.Timeout as exc:
            raise AlpacaAPIError("timeout Alpaca") from exc
        except requests.RequestException as exc:
            raise AlpacaAPIError(f"transport Alpaca indisponible: {exc}") from exc

        status = getattr(response, "status_code", None)
        if status is None:
            raise AlpacaAPIError("reponse Alpaca invalide: status_code absent")
        if status >= 400:
            reason = _safe_error_text(response)
            raise AlpacaAPIError(f"Alpaca HTTP {status}: {reason}")

        try:
            return response.json()
        except ValueError as exc:
            raise AlpacaAPIError("reponse Alpaca non JSON") from exc


def _safe_error_text(response: Any) -> str:
    try:
        data = response.json()
    except ValueError:
        text = str(getattr(response, "text", "")).strip()
        return text[:240] if text else "erreur sans corps"
    if isinstance(data, dict):
        for key in ("message", "error", "reject_reason", "code"):
            if data.get(key):
                return str(data[key])[:240]
    return str(data)[:240]


def market_unavailable(exc: AlpacaAPIError) -> MarketDataUnavailable:
    return MarketDataUnavailable(str(exc))


def broker_unavailable(exc: AlpacaAPIError) -> BrokerUnavailable:
    return BrokerUnavailable(str(exc))

