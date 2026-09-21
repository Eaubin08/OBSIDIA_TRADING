"""
Bootstrap Monte Carlo sur serie de retours reelle.

Port (EXTRACT_PATTERN_ONLY) de `sim_lite_bootstrap` / `max_drawdown_from_returns`
(MVP-obsidia-, src/simulation/sim_lite.py). Contrairement a la source TS
de trading_world/ (trajectoires synthetiques parametriques), ce module
ne fait AUCUNE hypothese de modele : il reechantillonne avec remise des
fenetres de la serie de retours REELLE fournie en entree. Le dataset
factice de MVP-obsidia- (BTC_1h.csv, 48 lignes synthetiques) n'est PAS
porte — seule la logique de bootstrap l'est, elle accepte n'importe quelle
serie de retours numpy.

Complementarite avec simulation/trading_world/ documentee dans
docs/MIGRATION_PROVENANCE.md (section F4) : ce module est le moteur
PRINCIPAL des lors qu'un historique de marche reel est disponible
(hypothese-free) ; trading_world/ reste complementaire pour generer des
scenarios synthetiques parametriques (stress tests, "et si" sans donnees
reelles).

Cette couche ne decide et n'execute jamais rien.
"""
from __future__ import annotations

from typing import Optional

import numpy as np


def max_drawdown_from_returns(returns: np.ndarray) -> float:
    equity = np.cumprod(1.0 + returns)
    peak = equity[0] if len(equity) else 1.0
    max_dd = 0.0
    for v in equity:
        peak = max(peak, v)
        dd = 1.0 - v / peak
        max_dd = max(max_dd, float(dd))
    return float(max_dd)


def bootstrap_forecast(
    returns: np.ndarray,
    n_sims: int = 200,
    horizon: int = 20,
    bootstrap_window: int = 200,
    dd_threshold: float = 0.05,
    ruin_threshold: float = 0.10,
    seed: Optional[int] = None,
) -> dict:
    """
    Reechantillonne (bootstrap, avec remise) la fenetre glissante la plus
    recente de `returns` pour produire `n_sims` trajectoires de longueur
    `horizon`, et en deduit mu/sigma/P(drawdown)/P(ruine)/CVaR95.

    `seed` est optionnel (la source MVP-obsidia- originale utilisait
    `np.random` global, non seede). Passer un seed rend l'appel
    reproductible via `numpy.random.default_rng(seed)` ; ne pas en passer
    reproduit le comportement non deterministe de la source.
    """
    rng = np.random.default_rng(seed) if seed is not None else np.random

    if len(returns) == 0:
        return {
            "mu": 0.0,
            "sigma": 0.0,
            "p_dd": 0.0,
            "p_ruin": 0.0,
            "cvar_95": 0.0,
            "n_sims": 0,
            "horizon": horizon,
        }

    window = returns[-bootstrap_window:] if len(returns) >= bootstrap_window else returns
    horizon = min(horizon, len(window))
    sims = rng.choice(window, size=(n_sims, horizon), replace=True)
    cum = np.cumsum(sims, axis=1)
    final = cum[:, -1]

    p_dd = 0.0
    p_ruin = 0.0
    dd_vals = []
    for i in range(n_sims):
        rpath = sims[i]
        dd = max_drawdown_from_returns(rpath)
        dd_vals.append(dd)
        if dd > dd_threshold:
            p_dd += 1.0
        if np.min(cum[i]) < -ruin_threshold:
            p_ruin += 1.0

    p_dd /= n_sims
    p_ruin /= n_sims

    q = np.percentile(final, 5)
    tail = final[final <= q]
    cvar_95 = float(np.mean(tail)) if len(tail) else float(q)

    return {
        "mu": float(np.mean(final)),
        "sigma": float(np.std(final)),
        "p_dd": float(p_dd),
        "p_ruin": float(p_ruin),
        "cvar_95": float(cvar_95),
        "n_sims": int(n_sims),
        "horizon": int(horizon),
        "dd_threshold": float(dd_threshold),
        "ruin_threshold": float(ruin_threshold),
        "dd_mean": float(np.mean(dd_vals)) if dd_vals else 0.0,
    }
