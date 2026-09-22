"""
F13 (suite) — tests unitaires purs (aucun reseau) pour
domain/calibration_estimation.py : determinisme, seuils d'insuffisance de
donnees, non-invention de valeurs, et absence d'import gouvernance/Binder.
"""
from __future__ import annotations

import ast
import math
from pathlib import Path

from domain.calibration_estimation import (
    estimate_garch_1_1,
    estimate_markov_regime_matrix,
    estimate_realized_volatility,
    log_returns_from_closes,
)


def _synthetic_returns(n: int, seed: int = 42) -> list:
    """Sequence deterministe (PRNG local, pas numpy.random global) — sert
    uniquement a tester les proprietes mathematiques des estimateurs, ne
    pretend jamais representer un marche reel."""
    x = seed
    out = []
    for _ in range(n):
        x = (1103515245 * x + 12345) % (2**31)
        out.append((x / (2**31) - 0.5) * 0.02)
    return out


def test_log_returns_from_closes_basic():
    closes = [100.0, 101.0, 100.5, 102.0]
    returns = log_returns_from_closes(closes)
    assert len(returns) == 3
    assert math.isclose(returns[0], math.log(101.0 / 100.0))


def test_log_returns_skips_non_positive_prices():
    closes = [100.0, 0.0, 101.0]
    returns = log_returns_from_closes(closes)
    # les deux paires (100,0) et (0,101) impliquent un prix <=0 : les deux
    # sont ignorees (aucun rendement ne peut etre calcule autour de 0).
    assert len(returns) == 0


def test_volatility_estimate_deterministic():
    returns = _synthetic_returns(50)
    v1 = estimate_realized_volatility(returns)
    v2 = estimate_realized_volatility(returns)
    assert v1.annualized_vol == v2.annualized_vol
    assert v1.sufficient_data is True


def test_volatility_insufficient_below_threshold():
    v = estimate_realized_volatility(_synthetic_returns(5))
    assert v.sufficient_data is False
    assert v.annualized_vol == 0.0


def test_garch_deterministic_same_input():
    returns = _synthetic_returns(60)
    g1 = estimate_garch_1_1(returns)
    g2 = estimate_garch_1_1(returns)
    assert g1.omega == g2.omega
    assert g1.alpha == g2.alpha
    assert g1.beta == g2.beta


def test_garch_stationarity_constraint():
    returns = _synthetic_returns(80)
    g = estimate_garch_1_1(returns)
    assert g.sufficient_data
    assert g.alpha + g.beta < 1.0
    assert g.omega > 0.0


def test_garch_insufficient_below_threshold():
    g = estimate_garch_1_1(_synthetic_returns(10))
    assert g.sufficient_data is False
    assert g.omega == 0.0 and g.alpha == 0.0 and g.beta == 0.0


def test_markov_deterministic_and_rows_sum_to_one():
    returns = _synthetic_returns(60)
    m1 = estimate_markov_regime_matrix(returns, n_regimes=2)
    m2 = estimate_markov_regime_matrix(returns, n_regimes=2)
    assert m1.transition_matrix == m2.transition_matrix
    assert m1.sufficient_data
    for row in m1.transition_matrix:
        assert abs(sum(row) - 1.0) < 1e-9


def test_markov_insufficient_below_threshold():
    m = estimate_markov_regime_matrix(_synthetic_returns(10), n_regimes=2)
    assert m.sufficient_data is False
    assert m.transition_matrix == tuple()


def test_markov_observation_count_matches_sample():
    returns = _synthetic_returns(60)
    m = estimate_markov_regime_matrix(returns, n_regimes=2)
    assert sum(m.observations_per_regime) == len(returns)


# aucun import governance/ ni execution.binder dans le module d'estimation
def test_no_governance_or_binder_import_in_estimation_module():
    tree = ast.parse(Path("domain/calibration_estimation.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", None) or ",".join(n.name for n in node.names)
            assert "governance" not in (mod or "")
            assert "execution.binder" not in (mod or "")
