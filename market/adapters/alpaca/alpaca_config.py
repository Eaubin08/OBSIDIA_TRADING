"""Configuration Alpaca explicite, environnement uniquement."""
from __future__ import annotations

import os
from dataclasses import dataclass

from domain.types import Mode


class AlpacaConfigurationError(ValueError):
    """Configuration Alpaca invalide ou incomplete."""


@dataclass(frozen=True)
class AlpacaConfig:
    mode: Mode
    api_key: str
    secret_key: str
    trading_base_url: str
    data_base_url: str = "https://data.alpaca.markets"
    data_feed: str = "iex"
    crypto_location: str = "us"
    timeout_s: float = 10.0

    @classmethod
    def from_env(cls, *, require_credentials: bool = True) -> "AlpacaConfig":
        raw_mode = os.getenv("ALPACA_MODE", "paper").strip().lower()
        if raw_mode == "paper":
            mode = Mode.PAPER
            default_trading = "https://paper-api.alpaca.markets"
        elif raw_mode == "live":
            mode = Mode.LIVE
            default_trading = "https://api.alpaca.markets"
        else:
            raise AlpacaConfigurationError(
                "ALPACA_MODE doit valoir 'paper' ou 'live'"
            )

        api_key = os.getenv("ALPACA_API_KEY", "").strip()
        secret_key = os.getenv("ALPACA_SECRET_KEY", "").strip()
        if require_credentials and (not api_key or not secret_key):
            raise AlpacaConfigurationError(
                "ALPACA_API_KEY et ALPACA_SECRET_KEY sont requis pour Alpaca"
            )

        timeout_raw = os.getenv("ALPACA_TIMEOUT_S", "10.0").strip()
        try:
            timeout_s = float(timeout_raw)
        except ValueError as exc:
            raise AlpacaConfigurationError(
                f"ALPACA_TIMEOUT_S invalide: {timeout_raw!r}"
            ) from exc
        if timeout_s <= 0:
            raise AlpacaConfigurationError("ALPACA_TIMEOUT_S doit etre positif")

        return cls(
            mode=mode,
            api_key=api_key,
            secret_key=secret_key,
            trading_base_url=os.getenv(
                "ALPACA_TRADING_BASE_URL", default_trading
            ).rstrip("/"),
            data_base_url=os.getenv(
                "ALPACA_DATA_BASE_URL", "https://data.alpaca.markets"
            ).rstrip("/"),
            data_feed=os.getenv("ALPACA_DATA_FEED", "iex").strip() or "iex",
            crypto_location=os.getenv("ALPACA_CRYPTO_LOCATION", "us").strip() or "us",
            timeout_s=timeout_s,
        )

    def auth_headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
        }

