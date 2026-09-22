"""
F13 — estimation de parametres de domaine a partir de rendements reels.

Fonctions pures : entree = sequence de log-rendements deja calcules a partir
de prix de cloture reels (obtenus ailleurs, ex. market/adapters/alpaca/
real_dataset_attempt.py). Aucune de ces fonctions n'importe governance/ ni
execution/binder/, et aucune ne recoit ou ne lit un verdict KX108 — la
calibration precede et ignore totalement l'autorite (verifie par
tests/unit/test_calibration_estimation.py::test_no_kernel_verdict_import).

Chaque fonction est honnete sur l'insuffisance de donnees : en dessous d'un
seuil minimal d'observations, elle retourne un statut UNCALIBRATED/sparse
plutot que d'inventer un parametre.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence, Tuple

MIN_OBSERVATIONS_VOLATILITY = 10
MIN_OBSERVATIONS_GARCH = 30
MIN_OBSERVATIONS_MARKOV = 30


def log_returns_from_closes(closes: Sequence[float]) -> List[float]:
    """Rendements log consecutifs. `closes` doit etre en ordre chronologique."""
    out: List[float] = []
    for prev, cur in zip(closes, closes[1:]):
        if prev <= 0 or cur <= 0:
            continue
        out.append(math.log(cur / prev))
    return out


@dataclass(frozen=True)
class VolatilityEstimate:
    sufficient_data: bool
    annualized_vol: float
    sample_size: int
    method: str


def estimate_realized_volatility(
    returns: Sequence[float], periods_per_year: int = 252
) -> VolatilityEstimate:
    """Ecart-type empirique des rendements, annualise par sqrt(periods_per_year)."""
    n = len(returns)
    if n < MIN_OBSERVATIONS_VOLATILITY:
        return VolatilityEstimate(
            sufficient_data=False, annualized_vol=0.0, sample_size=n,
            method=f"sample_stdev (insuffisant: {n} < {MIN_OBSERVATIONS_VOLATILITY} observations requises)",
        )
    mean = sum(returns) / n
    var = sum((r - mean) ** 2 for r in returns) / (n - 1)
    daily_vol = math.sqrt(var)
    return VolatilityEstimate(
        sufficient_data=True,
        annualized_vol=daily_vol * math.sqrt(periods_per_year),
        sample_size=n,
        method=f"sample_stdev annualise sqrt({periods_per_year}), echantillon={n}",
    )


@dataclass(frozen=True)
class GarchEstimate:
    sufficient_data: bool
    omega: float
    alpha: float
    beta: float
    sample_size: int
    negative_log_likelihood: float
    method: str


def _garch_nll(returns: Sequence[float], omega: float, alpha: float, beta: float) -> float:
    """Log-vraisemblance negative gaussienne pour une trajectoire GARCH(1,1)."""
    var = sum(r * r for r in returns) / len(returns)
    nll = 0.0
    prev_r2 = 0.0
    for r in returns:
        var = omega + alpha * prev_r2 + beta * var
        var = max(var, 1e-10)
        nll += 0.5 * (math.log(var) + (r * r) / var)
        prev_r2 = r * r
    return nll


def estimate_garch_1_1(returns: Sequence[float]) -> GarchEstimate:
    """
    Calibration GARCH(1,1) par recherche en grille sur (alpha, beta) sous
    contrainte alpha+beta<1 (stationnarite), omega fixe par variance
    targeting (omega = (1-alpha-beta) * variance_inconditionnelle) —
    methode simple et documentee, pas une MLE complete, mais un vrai
    ajustement sur les donnees (minimisation de la NLL gaussienne), pas des
    coefficients devines.
    """
    n = len(returns)
    if n < MIN_OBSERVATIONS_GARCH:
        return GarchEstimate(
            sufficient_data=False, omega=0.0, alpha=0.0, beta=0.0, sample_size=n,
            negative_log_likelihood=0.0,
            method=f"grid_search_variance_targeting (insuffisant: {n} < {MIN_OBSERVATIONS_GARCH} observations requises)",
        )
    unconditional_var = sum(r * r for r in returns) / n
    best = None
    alpha_grid = [0.02, 0.05, 0.08, 0.12, 0.16, 0.20]
    beta_grid = [0.60, 0.70, 0.75, 0.80, 0.85, 0.90]
    for alpha in alpha_grid:
        for beta in beta_grid:
            if alpha + beta >= 0.999:
                continue
            omega = (1.0 - alpha - beta) * unconditional_var
            nll = _garch_nll(returns, omega, alpha, beta)
            if best is None or nll < best[0]:
                best = (nll, omega, alpha, beta)
    assert best is not None
    nll, omega, alpha, beta = best
    return GarchEstimate(
        sufficient_data=True, omega=omega, alpha=alpha, beta=beta, sample_size=n,
        negative_log_likelihood=nll,
        method=(
            "grid_search_variance_targeting: omega=(1-alpha-beta)*var_inconditionnelle, "
            f"grille alpha={alpha_grid} x beta={beta_grid}, minimisation NLL gaussienne"
        ),
    )


@dataclass(frozen=True)
class MarkovEstimate:
    sufficient_data: bool
    n_regimes: int
    transition_matrix: Tuple[Tuple[float, ...], ...]
    regime_thresholds: Tuple[float, ...]
    observations_per_regime: Tuple[int, ...]
    method: str


def estimate_markov_regime_matrix(
    returns: Sequence[float], n_regimes: int = 2
) -> MarkovEstimate:
    """
    Classe chaque rendement en regime par quantiles empiriques des valeurs
    absolues de rendement (proxy de volatilite realisee locale), puis compte
    les transitions observees regime[t] -> regime[t+1]. Lissage additif de
    Laplace (+1 sur chaque cellule) pour eviter les lignes a zero
    observation. C'est une methode simple et explicite, PAS une detection
    de "regime de marche vrai" — juste un decoupage empirique par magnitude
    de rendement, documente comme tel.
    """
    n = len(returns)
    if n < MIN_OBSERVATIONS_MARKOV:
        return MarkovEstimate(
            sufficient_data=False, n_regimes=n_regimes,
            transition_matrix=tuple(), regime_thresholds=tuple(),
            observations_per_regime=tuple(),
            method=f"quantile_classification (insuffisant: {n} < {MIN_OBSERVATIONS_MARKOV} observations requises)",
        )
    abs_returns = sorted(abs(r) for r in returns)
    thresholds = []
    for q in range(1, n_regimes):
        idx = min(int(q / n_regimes * len(abs_returns)), len(abs_returns) - 1)
        thresholds.append(abs_returns[idx])

    def _regime_of(r: float) -> int:
        a = abs(r)
        for i, t in enumerate(thresholds):
            if a <= t:
                return i
        return n_regimes - 1

    counts = [[1 for _ in range(n_regimes)] for _ in range(n_regimes)]  # Laplace +1
    obs_per_regime = [0] * n_regimes
    prev_regime = _regime_of(returns[0])
    obs_per_regime[prev_regime] += 1
    for r in returns[1:]:
        cur_regime = _regime_of(r)
        counts[prev_regime][cur_regime] += 1
        obs_per_regime[cur_regime] += 1
        prev_regime = cur_regime

    matrix = tuple(
        tuple(c / sum(row) for c in row) for row in counts
    )
    return MarkovEstimate(
        sufficient_data=True, n_regimes=n_regimes,
        transition_matrix=matrix,
        regime_thresholds=tuple(thresholds),
        observations_per_regime=tuple(obs_per_regime),
        method=(
            f"quantile_classification sur |rendement| ({n_regimes} regimes, seuils par quantiles empiriques), "
            f"comptage de transitions regime[t]->regime[t+1], lissage de Laplace (+1 par cellule), echantillon={n}"
        ),
    )
