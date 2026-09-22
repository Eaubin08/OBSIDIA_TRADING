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
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from domain.calibration import DatasetDescriptor

DATA_BASE_URL = "https://data.alpaca.markets"


def _default_window(lookback_days: int) -> Tuple[str, str]:
    """
    Sans `start` explicite, l'endpoint Alpaca ne retourne quasi rien (observe
    en F13 : `limit=200` sans `start` -> 1 seule barre, la plus recente).
    Fenetre par defaut : `lookback_days` jours calendaires se terminant hier
    (evite les soucis de barre du jour courant partiellement formee).
    """
    end = datetime.now(timezone.utc) - timedelta(days=1)
    start = end - timedelta(days=lookback_days)
    return start.strftime("%Y-%m-%dT00:00:00Z"), end.strftime("%Y-%m-%dT00:00:00Z")


def attempt_real_historical_dataset(
    symbol: str = "AAPL", timeframe: str = "1Day", limit: int = 100,
    lookback_days: int = 200,
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
    window_start, window_end = _default_window(lookback_days)
    params = {
        "timeframe": timeframe, "limit": limit, "feed": "iex",
        "start": window_start, "end": window_end,
    }

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


def attempt_real_historical_dataset_with_closes(
    symbol: str = "AAPL", timeframe: str = "1Day", limit: int = 100,
    lookback_days: int = 200,
) -> Tuple[DatasetDescriptor, List[float]]:
    """
    Meme comportement honnete que `attempt_real_historical_dataset`, mais
    renvoie en plus la liste des prix de cloture reellement recus (ordre
    chronologique), necessaire pour estimer des parametres de domaine
    (domain/calibration_estimation.py). Liste vide si observation_count==0.
    """
    retrieved_at = datetime.now(timezone.utc).isoformat()
    api_key = os.environ.get("ALPACA_API_KEY", "").strip()
    secret_key = os.environ.get("ALPACA_SECRET_KEY", "").strip()

    if not api_key or not secret_key:
        return DatasetDescriptor(
            source="alpaca_market_data_api", symbol=symbol, timeframe=timeframe,
            start=None, end=None, observation_count=0, retrieved_at=retrieved_at,
            quality_flags=("NO_CREDENTIALS_CONFIGURED",),
        ), []

    try:
        import requests
    except ImportError:
        return DatasetDescriptor(
            source="alpaca_market_data_api", symbol=symbol, timeframe=timeframe,
            start=None, end=None, observation_count=0, retrieved_at=retrieved_at,
            quality_flags=("REQUESTS_MODULE_UNAVAILABLE",),
        ), []

    url = f"{DATA_BASE_URL}/v2/stocks/{symbol}/bars"
    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key}
    window_start, window_end = _default_window(lookback_days)
    params = {
        "timeframe": timeframe, "limit": limit, "feed": "iex",
        "start": window_start, "end": window_end,
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15.0)
    except Exception as exc:
        return DatasetDescriptor(
            source="alpaca_market_data_api", symbol=symbol, timeframe=timeframe,
            start=None, end=None, observation_count=0, retrieved_at=retrieved_at,
            quality_flags=(f"TRANSPORT_ERROR:{type(exc).__name__}",),
        ), []

    if response.status_code != 200:
        return DatasetDescriptor(
            source="alpaca_market_data_api", symbol=symbol, timeframe=timeframe,
            start=None, end=None, observation_count=0, retrieved_at=retrieved_at,
            quality_flags=(f"HTTP_{response.status_code}",),
        ), []

    try:
        payload = response.json()
        bars = payload.get("bars", [])
    except Exception as exc:
        return DatasetDescriptor(
            source="alpaca_market_data_api", symbol=symbol, timeframe=timeframe,
            start=None, end=None, observation_count=0, retrieved_at=retrieved_at,
            quality_flags=(f"MALFORMED_RESPONSE:{type(exc).__name__}",),
        ), []

    if not bars:
        return DatasetDescriptor(
            source="alpaca_market_data_api", symbol=symbol, timeframe=timeframe,
            start=None, end=None, observation_count=0, retrieved_at=retrieved_at,
            quality_flags=("EMPTY_RESPONSE",),
        ), []

    closes = [float(b["c"]) for b in bars if "c" in b]
    descriptor = DatasetDescriptor(
        source="alpaca_market_data_api",
        symbol=symbol,
        timeframe=timeframe,
        start=bars[0].get("t"),
        end=bars[-1].get("t"),
        observation_count=len(bars),
        retrieved_at=retrieved_at,
        quality_flags=() if len(closes) == len(bars) else ("SOME_BARS_MISSING_CLOSE_FIELD",),
    )
    return descriptor, closes
