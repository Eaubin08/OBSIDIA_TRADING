"""
TradingWorld engine — port Python fidele du moteur TypeScript
Obsidia-lab-trad (os4-platform/server/engines/tradingEngine.ts, mars 2026).

Modele de prix composite : GBM a parametres dependants du regime + chaine
de Markov + volatilite GARCH(1,1) + sauts de Merton. PRNG seede pour
replay deterministe exact.

Cette couche est une SIMULATION : elle observe/calcule des scenarios et
des metriques, elle ne decide et n'execute jamais rien. Aucun import vers
execution.binder ou market.adapters.alpaca n'est autorise ici.

AVERTISSEMENT (herite de la source TS sans correction) : la matrice de
transition de Markov (`build_regime_matrix`) est construite aleatoirement
a partir du seed, PAS calibree sur des donnees de marche reelles. C'est un
squelette fonctionnel demontrant le mecanisme markovien, pas un modele de
regime valide empiriquement. Voir docs/B15_STRUCTURAL_SCORE_BOUNDARY.md
pour le meme type de limite documentee sur un autre composant.
"""
from simulation.trading_world.rng import Mulberry32, box_muller
from simulation.trading_world.market_process import (
    TradingParams,
    TradingStep,
    run_trading_simulation,
    build_regime_matrix,
)
from simulation.trading_world.risk_metrics import (
    TradingMetrics,
    compute_trading_metrics,
    max_drawdown,
    value_at_risk_95,
    expected_shortfall_95,
    sharpe_ratio,
    merkle_root,
)

__all__ = [
    "Mulberry32",
    "box_muller",
    "TradingParams",
    "TradingStep",
    "run_trading_simulation",
    "build_regime_matrix",
    "TradingMetrics",
    "compute_trading_metrics",
    "max_drawdown",
    "value_at_risk_95",
    "expected_shortfall_95",
    "sharpe_ratio",
    "merkle_root",
]
