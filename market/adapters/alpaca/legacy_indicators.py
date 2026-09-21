"""
Obsidia x ERC-8004 — Indicators Library
Indicateurs techniques déterministes pour les 14 agents.
Source : agents/indicators.py du patch + métriques structurelles du moteur Obsidia.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from statistics import mean, pstdev
from typing import Deque, Iterable, List, Optional


# ─────────────────────────────────────────────
# Indicateurs techniques classiques
# ─────────────────────────────────────────────

def sma(values: Iterable[float], period: int) -> Optional[float]:
    values = list(values)
    if len(values) < period or period <= 0:
        return None
    return sum(values[-period:]) / period


def ema(values: Iterable[float], period: int) -> Optional[float]:
    values = list(values)
    if len(values) < period or period <= 0:
        return None
    k = 2 / (period + 1)
    out = values[0]
    for v in values[1:]:
        out = v * k + out * (1 - k)
    return out


def rsi(values: Iterable[float], period: int = 14) -> Optional[float]:
    prices = list(values)
    if len(prices) < period + 1:
        return None
    gains, losses = [], []
    for i in range(-period, 0):
        delta = prices[i] - prices[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(abs(min(delta, 0.0)))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(
    values: Iterable[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    prices = list(values)
    if len(prices) < slow + signal:
        return None, None, None
    macd_series: List[float] = []
    for i in range(slow, len(prices) + 1):
        window = prices[:i]
        fast_ema = ema(window, fast)
        slow_ema = ema(window, slow)
        if fast_ema is None or slow_ema is None:
            continue
        macd_series.append(fast_ema - slow_ema)
    if len(macd_series) < signal:
        return None, None, None
    macd_line = macd_series[-1]
    signal_line = ema(macd_series, signal)
    if signal_line is None:
        return None, None, None
    return macd_line, signal_line, macd_line - signal_line


def atr(
    highs: Iterable[float],
    lows: Iterable[float],
    closes: Iterable[float],
    period: int = 14,
) -> Optional[float]:
    highs, lows, closes = list(highs), list(lows), list(closes)
    if len(highs) < period + 1:
        return None
    trs: List[float] = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    return sum(trs[-period:]) / period


def bollinger(
    values: Iterable[float], period: int = 20, mult: float = 2.0
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    prices = list(values)
    if len(prices) < period:
        return None, None, None
    window = prices[-period:]
    mid = sum(window) / period
    std = pstdev(window)
    return mid - mult * std, mid, mid + mult * std


def zscore(values: Iterable[float], period: int = 20) -> Optional[float]:
    prices = list(values)
    if len(prices) < period:
        return None
    window = prices[-period:]
    m = mean(window)
    std = pstdev(window)
    if std == 0:
        return 0.0
    return (window[-1] - m) / std


def realized_volatility(values: Iterable[float], period: int = 20) -> Optional[float]:
    prices = list(values)
    if len(prices) < period + 1:
        return None
    rets = []
    for i in range(-period, 0):
        prev = prices[i - 1]
        if prev == 0:
            continue
        rets.append((prices[i] - prev) / prev)
    if len(rets) < 2:
        return None
    return pstdev(rets)


# ─────────────────────────────────────────────
# Métriques structurelles Obsidia (OS2)
# Adaptées du moteur Obsidia-lab-trad v18.3
# Utilisées par le Guard X-108 pour la cohésion
# ─────────────────────────────────────────────

def triangle_mean(W: List[List[float]], theta: float = 0.0) -> float:
    """Score de clôture triangulaire (cohésion locale entre agents)."""
    n = len(W)
    triangles = []
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(j + 1, n):
                t = (W[i][j] + W[j][k] + W[k][i]) / 3.0
                if t >= theta:
                    triangles.append(t)
    return sum(triangles) / len(triangles) if triangles else 0.0


def asymmetry_penalty(W: List[List[float]]) -> float:
    """Pénalité d'asymétrie (anti-domination d'un seul agent)."""
    degrees = [sum(row) for row in W]
    m = sum(degrees) / len(degrees)
    return sum(abs(d - m) for d in degrees) / len(degrees)


def structural_score(
    W: List[List[float]],
    alpha: float = 1.0,
    beta: float = 1.0,
    gamma: float = 0.5,
) -> float:
    """
    Score structurel normalise dans [0, 1].

    T = triangle_mean (cohesion locale)
    H = densite de connexion (proxy meso)
    A = asymetrie normalisee (penalite anti-domination)

    L'ancien calcul soustrayait directement A, mesuree comme dispersion de
    degres, a T/H, mesures de coherence bornees. Cette difference d'echelle
    rendait le score negatif dans des cas ordinaires et pouvait penaliser une
    majorite claire plus fortement qu'un quasi-split. On ramene donc A sur
    l'echelle [0, 1] avant de l'utiliser comme remise multiplicative.
    """
    if not W:
        return 0.0

    n = len(W)
    T = triangle_mean(W)
    H = sum(sum(row) for row in W) / n**2
    A = asymmetry_penalty(W)
    A_norm = A / max(n - 1, 1)

    weighted_cohesion = (alpha * T + beta * H) / max(alpha + beta, 1e-12)
    discounted = weighted_cohesion * max(0.0, 1.0 - gamma * A_norm)
    return max(0.0, min(1.0, discounted))


# ─────────────────────────────────────────────
# MarketState : fenêtre glissante de données
# ─────────────────────────────────────────────

@dataclass
class MarketState:
    symbol: str
    prices: Deque[float] = field(default_factory=lambda: deque(maxlen=300))
    highs: Deque[float] = field(default_factory=lambda: deque(maxlen=300))
    lows: Deque[float] = field(default_factory=lambda: deque(maxlen=300))
    volumes: Deque[float] = field(default_factory=lambda: deque(maxlen=300))
    spreads_bps: Deque[float] = field(default_factory=lambda: deque(maxlen=300))
    order_book_imbalances: Deque[float] = field(default_factory=lambda: deque(maxlen=300))
    sentiment_scores: Deque[float] = field(default_factory=lambda: deque(maxlen=300))
    event_risk_scores: Deque[float] = field(default_factory=lambda: deque(maxlen=300))
    btc_reference_prices: Deque[float] = field(default_factory=lambda: deque(maxlen=300))

    def update(
        self,
        *,
        price: float,
        high: float,
        low: float,
        volume: float,
        spread_bps: float,
        order_book_imbalance: float,
        sentiment_score: float,
        event_risk: float,
        btc_reference_price: Optional[float] = None,
    ) -> None:
        self.prices.append(price)
        self.highs.append(high)
        self.lows.append(low)
        self.volumes.append(volume)
        self.spreads_bps.append(spread_bps)
        self.order_book_imbalances.append(order_book_imbalance)
        self.sentiment_scores.append(sentiment_score)
        self.event_risk_scores.append(event_risk)
        self.btc_reference_prices.append(
            btc_reference_price if btc_reference_price is not None else price
        )

    # ─── Propriétés calculées (équivalents scalaires des Deques) ────────────────
    @property
    def price(self) -> float:
        return self.prices[-1] if self.prices else 0.0

    @property
    def high(self) -> Optional[float]:
        return self.highs[-1] if self.highs else None

    @property
    def low(self) -> Optional[float]:
        return self.lows[-1] if self.lows else None

    @property
    def volume(self) -> Optional[float]:
        return self.volumes[-1] if self.volumes else None

    @property
    def spread_bps(self) -> float:
        return self.spreads_bps[-1] if self.spreads_bps else 0.0

    @property
    def order_book_imbalance(self) -> float:
        return self.order_book_imbalances[-1] if self.order_book_imbalances else 0.0

    @property
    def sentiment_score(self) -> float:
        return self.sentiment_scores[-1] if self.sentiment_scores else 0.0

    @property
    def event_risk(self) -> float:
        return self.event_risk_scores[-1] if self.event_risk_scores else 0.0

    @property
    def rsi(self) -> float:
        r = rsi(list(self.prices))
        return r if r is not None else 50.0

    @property
    def volatility(self) -> float:
        v = realized_volatility(list(self.prices))
        return v if v is not None else 0.0

    @property
    def sma20(self) -> Optional[float]:
        return sma(list(self.prices), 20)

    @property
    def sma50(self) -> Optional[float]:
        return sma(list(self.prices), 50)
