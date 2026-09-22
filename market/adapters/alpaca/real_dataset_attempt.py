"""
F13 — tentative honnete d'obtention de donnees de marche reelles via Alpaca.

Ce module ne fabrique JAMAIS de donnees. S'il ne peut pas obtenir de vraies
barres depuis Alpaca (pas de credentials, erreur reseau, 401/403...), il
retourne un `DatasetDescriptor` avec `observation_count=0` et un
`quality_flags` expliquant precisement pourquoi — jamais une valeur
inventee presentee comme reelle.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Tuple

from domain.calibration import DatasetDescriptor

DATA_BASE_URL = "https://data.alpaca.markets"


def attempt_real_historical_dataset(
    symbol: str = "AAPL", timeframe: str = "1Day", limit: int = 100
) -> DatasetDescriptor:
    """
    Tente d'obtenir de vraies barres historiques Alpaca. Retourne toujours
    un DatasetDescriptor honnete, jamais une exception qui masquerait le
    resultat au CalibrationPack.
    """
    retrieved_at = datetime.now(timezone.utc).isoformat()
    api_key = os.environ.get("ALPACA_API_KEY", "").strip()
    secret_key = os.environ.get("ALPACA_SECRET_KEY", "").strip()

    if not api_key or not secret_key:
        return DatasetDescriptor(
            source="alpaca_market_data_api",
            symbol=symbol,
            timeframe=timeframe,
            start=None,
            end=None,
            observation_count=0,
            retrieved_at=retrieved_at,
            quality_flags=("NO_CREDENTIALS_CONFIGURED",),
        )

    try:
        import requests
    except ImportError:
        return DatasetDescriptor(
            source="alpaca_market_data_api",
            symbol=symbol,
            timeframe=timeframe,
            start=None,
            end=None,
            observation_count=0,
            retrieved_at=retrieved_at,
            quality_flags=("REQUESTS_MODULE_UNAVAILABLE",),
        )

    url = f"{DATA_BASE_URL}/v2/stocks/{symbol}/bars"
    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key}
    params = {"timeframe": timeframe, "limit": limit}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10.0)
    except Exception as exc:  # transport failure : honnete, pas invente
        return DatasetDescriptor(
            source="alpaca_market_data_api", symbol=symbol, timeframe=timeframe,
            start=None, end=None, observation_count=0, retrieved_at=retrieved_at,
            quality_flags=(f"TRANSPORT_ERROR:{type(exc).__name__}",),
        )

    if response.status_code != 200:
        return DatasetDescriptor(
            source="alpaca_market_data_api", symbol=symbol, timeframe=timeframe,
            start=None, end=None, observation_count=0, retrieved_at=retrieved_at,
            quality_flags=(f"HTTP_{response.status_code}",),
        )

    try:
        payload = response.json()
        bars = payload.get("bars", [])
    except Exception as exc:
        return DatasetDescriptor(
            source="alpaca_market_data_api", symbol=symbol, timeframe=timeframe,
            start=None, end=None, observation_count=0, retrieved_at=retrieved_at,
            quality_flags=(f"MALFORMED_RESPONSE:{type(exc).__name__}",),
        )

    if not bars:
        return DatasetDescriptor(
            source="alpaca_market_data_api", symbol=symbol, timeframe=timeframe,
            start=None, end=None, observation_count=0, retrieved_at=retrieved_at,
            quality_flags=("EMPTY_RESPONSE",),
        )

    return DatasetDescriptor(
        source="alpaca_market_data_api",
        symbol=symbol,
        timeframe=timeframe,
        start=bars[0].get("t"),
        end=bars[-1].get("t"),
        observation_count=len(bars),
        retrieved_at=retrieved_at,
        quality_flags=(),
    )
