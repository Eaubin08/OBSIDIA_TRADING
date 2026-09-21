"""
Processus de prix composite : GBM a parametres dependants du regime +
chaine de Markov + volatilite GARCH(1,1) + sauts de Merton.

Port fidele des formules de la source TypeScript (Obsidia-lab-trad,
os4-platform/server/engines/tradingEngine.ts, runTradingSimulation +
buildRegimeMatrix, L77-170), verifiees par audit avant portage :

- GBM: gbmReturn = (mu_r - 0.5*sigma_r^2)*dt + sigma_r*sqrt(dt)*z
- Markov: matrice de transition normalisee, tirage cumulatif
- GARCH(1,1): garchVar = omega + alpha*prevReturn^2 + beta*garchVar
- Merton jump diffusion: jumpProb = lambda*dt, jumpReturn = jumpMu + jumpSigma*z

Cette couche ne decide et n'execute jamais rien : elle produit une
trajectoire de prix simulee et des metriques (voir risk_metrics.py) pour
alimenter le domaine et la gouvernance en scenarios, jamais pour agir.

AVERTISSEMENT : `build_regime_matrix` genere une matrice de transition a
partir du seed (self-transition favorisee par construction), PAS calibree
sur des donnees de marche reelles — identique a la limite deja presente
dans la source TS. A calibrer empiriquement avant tout usage au-dela de
la demonstration/du test.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from simulation.trading_world.rng import Mulberry32, box_muller


@dataclass(frozen=True)
class TradingParams:
    seed: int
    steps: int
    s0: float  # prix initial
    mu: float  # derive
    sigma: float  # volatilite de base
    dt: float  # pas de temps (ex: 1/252)
    jump_lambda: float  # intensite Poisson
    jump_mu: float  # taille de saut moyenne
    jump_sigma: float  # ecart-type de la taille de saut
    garch_alpha: float
    garch_beta: float
    garch_omega: float
    regimes: int  # nombre de regimes de Markov
    friction_bps: float  # cout de transaction en points de base


@dataclass(frozen=True)
class TradingStep:
    t: int
    price: float
    returns: float
    volatility: float
    regime: int
    jump: bool
    volume: float


def build_regime_matrix(n: int, rand) -> List[List[float]]:
    """
    Matrice de transition de Markov n x n, normalisee par ligne.

    NON CALIBREE : la diagonale (auto-transition) est artificiellement
    favorisee par construction (`+n` sur la diagonale, `+0.1` ailleurs),
    pas par une estimation sur des donnees de marche reelles. Squelette
    fonctionnel, pas un modele de regime valide.
    """
    matrix: List[List[float]] = []
    for i in range(n):
        row: List[float] = []
        total = 0.0
        for j in range(n):
            v = rand() + (n if i == j else 0.1)
            row.append(v)
            total += v
        matrix.append([v / total for v in row])
    return matrix


def run_trading_simulation(
    params: TradingParams,
) -> Tuple[List[TradingStep], List[float]]:
    """
    Simule une trajectoire de prix de `params.steps` pas.

    Retourne (steps, returns) — les metriques sont calculees separement
    par risk_metrics.compute_trading_metrics.
    """
    prng = Mulberry32(params.seed)
    rand = prng.random

    regime_transition = build_regime_matrix(params.regimes, rand)
    regime_mu = [
        params.mu * (1 + (i - params.regimes / 2) * 0.5)
        for i in range(params.regimes)
    ]
    regime_sigma = [
        params.sigma * (1 + i * 0.3) for i in range(params.regimes)
    ]

    steps: List[TradingStep] = []
    price = params.s0
    regime = 0
    garch_var = params.sigma * params.sigma
    returns: List[float] = []

    for t in range(params.steps):
        # 1. Transition de regime
        trans_row = regime_transition[regime]
        u = rand()
        cum_p = 0.0
        for r in range(params.regimes):
            cum_p += trans_row[r]
            if u < cum_p:
                regime = r
                break

        # 2. Mise a jour de la volatilite GARCH
        prev_return = returns[-1] if returns else 0.0
        garch_var = (
            params.garch_omega
            + params.garch_alpha * prev_return * prev_return
            + params.garch_beta * garch_var
        )
        garch_sigma = (max(garch_var, 1e-8)) ** 0.5

        # 3. GBM a parametres dependants du regime
        mu_r = regime_mu[regime]
        sigma_r = regime_sigma[regime] * garch_sigma / params.sigma
        z = box_muller(rand)
        gbm_return = (mu_r - 0.5 * sigma_r * sigma_r) * params.dt + sigma_r * (
            params.dt ** 0.5
        ) * z

        # 4. Sauts (Merton)
        jump_return = 0.0
        jumped = False
        jump_prob = params.jump_lambda * params.dt
        if rand() < jump_prob:
            jumped = True
            jz = box_muller(rand)
            jump_return = params.jump_mu + params.jump_sigma * jz

        # 5. Friction
        friction_cost = params.friction_bps / 10000.0 * (2 if jumped else 1)

        total_return = gbm_return + jump_return - friction_cost
        price = price * _exp(total_return)

        # 6. Volume (log-normal)
        volume = _exp(10 + 0.5 * box_muller(rand))

        returns.append(total_return)
        steps.append(
            TradingStep(
                t=t,
                price=max(price, 0.01),
                returns=total_return,
                volatility=garch_sigma,
                regime=regime,
                jump=jumped,
                volume=volume,
            )
        )

    return steps, returns


def _exp(x: float) -> float:
    import math

    return math.exp(x)
