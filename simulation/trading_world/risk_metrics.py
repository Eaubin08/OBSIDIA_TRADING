"""
Metriques de risque sur une trajectoire simulee.

Port fidele de computeTradingMetrics (tradingEngine.ts, L172-223) :
VaR historique, Expected Shortfall, Sharpe annualise, Max Drawdown,
empreinte d'etat (state hash) et racine de Merkle sur les prix.

Ces metriques sont des OBSERVATIONS calculees sur un scenario simule —
elles alimentent le domaine/la preuve (voir proof/), elles ne decident
jamais rien.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import List, Sequence

from simulation.trading_world.market_process import TradingParams, TradingStep


@dataclass(frozen=True)
class TradingMetrics:
    final_price: float
    total_return: float
    annualized_vol: float
    max_drawdown: float
    var_95: float
    es_95: float
    sharpe: float
    state_hash: str
    merkle_root: str


def max_drawdown(prices: Sequence[float], s0: float) -> float:
    """Port de la boucle peak/dd (tradingEngine.ts L185-192)."""
    peak = s0
    max_dd = 0.0
    for price in prices:
        if price > peak:
            peak = price
        dd = (peak - price) / peak
        if dd > max_dd:
            max_dd = dd
    return max_dd


def value_at_risk_95(returns: Sequence[float]) -> float:
    """VaR historique a 95% : quantile empirique des pertes (L195-197)."""
    if not returns:
        return 0.0
    sorted_returns = sorted(returns)
    idx = int(0.05 * len(sorted_returns))
    return -sorted_returns[idx]


def expected_shortfall_95(returns: Sequence[float]) -> float:
    """
    ES/CVaR a 95% : moyenne conditionnelle des pertes sous le quantile VaR
    (L198). Reproduit fidelement la source, y compris le garde-fou
    `idx or 1` pour eviter une division par zero sur de petits echantillons.
    """
    if not returns:
        return 0.0
    sorted_returns = sorted(returns)
    idx = int(0.05 * len(sorted_returns))
    tail = sorted_returns[:idx]
    denom = idx if idx else 1
    return -(sum(tail) / denom)


def sharpe_ratio(total_return: float, annualized_vol: float, steps: int, dt: float) -> float:
    """Sharpe annualise, taux sans risque = 0 (L200-202)."""
    annual_return = total_return / (steps * dt) if steps and dt else 0.0
    return annual_return / (annualized_vol + 1e-8)


def merkle_root(hashes: List[str]) -> str:
    """
    Racine de Merkle simple (reduction par paires SHA-256), equivalent a
    computeMerkleRoot importe de guardX108.ts dans la source. Le dernier
    element est duplique si le nombre de feuilles est impair.
    """
    if not hashes:
        return hashlib.sha256(b"").hexdigest()
    level = list(hashes)
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [
            hashlib.sha256((level[i] + level[i + 1]).encode("utf-8")).hexdigest()
            for i in range(0, len(level), 2)
        ]
    return level[0]


def compute_trading_metrics(
    steps: List[TradingStep], params: TradingParams, returns: List[float]
) -> TradingMetrics:
    final_price = steps[-1].price if steps else params.s0
    total_return = (final_price - params.s0) / params.s0

    n = len(returns)
    mean = sum(returns) / n if n else 0.0
    variance = sum((r - mean) ** 2 for r in returns) / n if n else 0.0
    annualized_vol = (variance / params.dt) ** 0.5 if params.dt else 0.0

    prices = [s.price for s in steps]
    max_dd = max_drawdown(prices, params.s0)

    var95 = value_at_risk_95(returns)
    es95 = expected_shortfall_95(returns)
    sharpe = sharpe_ratio(total_return, annualized_vol, params.steps, params.dt)

    state_str = "|".join(f"{s.t}:{s.price:.6f}:{s.regime}" for s in steps)
    state_hash = hashlib.sha256(state_str.encode("utf-8")).hexdigest()

    price_hashes = [
        hashlib.sha256(f"{s.price:.6f}".encode("utf-8")).hexdigest() for s in steps
    ]
    root = merkle_root(price_hashes)

    return TradingMetrics(
        final_price=final_price,
        total_return=total_return,
        annualized_vol=annualized_vol,
        max_drawdown=max_dd,
        var_95=var95,
        es_95=es95,
        sharpe=sharpe,
        state_hash=state_hash,
        merkle_root=root,
    )
