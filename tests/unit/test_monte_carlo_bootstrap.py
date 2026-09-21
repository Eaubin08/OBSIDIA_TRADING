"""
Tests unitaires pour simulation/monte_carlo/bootstrap.py (bootstrap sur
serie de retours reelle, porte depuis MVP-obsidia-).
"""
import numpy as np
import pytest

from simulation.monte_carlo.bootstrap import bootstrap_forecast, max_drawdown_from_returns


class TestMaxDrawdownFromReturns:
    def test_known_sequence(self):
        # equity: 1 -> 1.2 (pic) -> 1.2*0.75=0.9 -> dd = 1-0.9/1.2 = 0.25
        returns = np.array([0.20, -0.25])
        assert max_drawdown_from_returns(returns) == pytest.approx(0.25, abs=1e-9)

    def test_no_drawdown_on_monotonic_gains(self):
        returns = np.array([0.01, 0.02, 0.03])
        assert max_drawdown_from_returns(returns) == 0.0

    def test_empty_returns(self):
        assert max_drawdown_from_returns(np.array([])) == 0.0


class TestBootstrapForecast:
    def test_empty_returns_returns_zeroed_result(self):
        result = bootstrap_forecast(np.array([]))
        assert result["n_sims"] == 0
        assert result["mu"] == 0.0
        assert result["sigma"] == 0.0

    def test_deterministic_with_seed(self):
        returns = np.array([0.01, -0.02, 0.015, -0.005, 0.02, -0.01] * 40)
        result_a = bootstrap_forecast(returns, n_sims=50, horizon=10, seed=777)
        result_b = bootstrap_forecast(returns, n_sims=50, horizon=10, seed=777)
        assert result_a == result_b

    def test_different_seed_different_result(self):
        returns = np.array([0.01, -0.02, 0.015, -0.005, 0.02, -0.01] * 40)
        result_a = bootstrap_forecast(returns, n_sims=50, horizon=10, seed=1)
        result_b = bootstrap_forecast(returns, n_sims=50, horizon=10, seed=2)
        assert result_a["mu"] != result_b["mu"] or result_a["sigma"] != result_b["sigma"]

    def test_result_shape_and_keys(self):
        returns = np.random.default_rng(0).normal(0.0005, 0.01, size=300)
        result = bootstrap_forecast(returns, n_sims=100, horizon=15, seed=42)
        expected_keys = {
            "mu", "sigma", "p_dd", "p_ruin", "cvar_95",
            "n_sims", "horizon", "dd_threshold", "ruin_threshold", "dd_mean",
        }
        assert set(result.keys()) == expected_keys
        assert result["n_sims"] == 100
        assert result["horizon"] == 15
        assert 0.0 <= result["p_dd"] <= 1.0
        assert 0.0 <= result["p_ruin"] <= 1.0

    def test_accepts_real_return_series_not_just_mvp_dataset(self):
        """Le module doit fonctionner sur n'importe quelle serie de retours
        reelle, pas seulement le dataset factice BTC_1h.csv de MVP-obsidia-
        (qui n'est volontairement pas porte)."""
        real_like_returns = np.array([0.003, -0.012, 0.021, 0.004, -0.030, 0.011, 0.002] * 30)
        result = bootstrap_forecast(real_like_returns, n_sims=200, horizon=20, seed=2026)
        assert result["n_sims"] == 200
        assert isinstance(result["cvar_95"], float)
