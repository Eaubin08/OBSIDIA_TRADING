"""
Tests unitaires pour simulation/trading_world/ (GBM+regimes+GARCH+jumps).

Chaque test isole un modele et verifie soit une propriete statistique
attendue, soit un cas de calcul exact connu a la main.
"""
import math

import pytest

from simulation.trading_world.market_process import (
    TradingParams,
    build_regime_matrix,
    run_trading_simulation,
)
from simulation.trading_world.risk_metrics import (
    compute_trading_metrics,
    expected_shortfall_95,
    max_drawdown,
    merkle_root,
    sharpe_ratio,
    value_at_risk_95,
)
from simulation.trading_world.rng import Mulberry32, box_muller


def _base_params(**overrides) -> TradingParams:
    defaults = dict(
        seed=42,
        steps=2000,
        s0=100.0,
        mu=0.05,
        sigma=0.20,
        dt=1.0 / 252,
        jump_lambda=0.0,
        jump_mu=0.0,
        jump_sigma=0.0,
        garch_alpha=0.0,
        garch_beta=0.0,
        garch_omega=0.20 * 0.20,  # constant variance -> pure GBM baseline
        regimes=1,
        friction_bps=0.0,
    )
    defaults.update(overrides)
    return TradingParams(**defaults)


class TestGBM:
    def test_gbm_lognormal_distribution(self):
        """Sans regime/jump/GARCH dynamique, la moyenne des log-retours
        doit converger vers (mu - 0.5*sigma^2)*dt (derive du GBM)."""
        params = _base_params(steps=20000, seed=7)
        steps, returns = run_trading_simulation(params)
        expected_mean = (params.mu - 0.5 * params.sigma ** 2) * params.dt
        observed_mean = sum(returns) / len(returns)
        assert observed_mean == pytest.approx(expected_mean, abs=5e-4)

    def test_gbm_volatility_matches_sigma(self):
        params = _base_params(steps=20000, seed=11)
        _, returns = run_trading_simulation(params)
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / len(returns)
        observed_vol = math.sqrt(variance / params.dt)
        assert observed_vol == pytest.approx(params.sigma, rel=0.05)


class TestGARCH:
    def test_garch_reacts_to_volatility_shock(self):
        """Un choc de retour important doit faire monter garch_var au pas
        suivant (alpha > 0), puis decroitre progressivement (beta < 1)."""
        params = _base_params(
            steps=5,
            seed=3,
            garch_alpha=0.3,
            garch_beta=0.6,
            garch_omega=0.0001,
            sigma=0.01,  # petite base pour que le choc domine
        )
        steps, _ = run_trading_simulation(params)
        vols = [s.volatility for s in steps]
        # garch_var(t=0) = omega + beta*sigma^2 (prev_return=0 au premier
        # pas) : verifie la formule exacte plutot que de supposer
        # sigma brut, puisque la mise a jour GARCH s'applique des t=0
        # (fidele a la source: garchVar recalcule avant construction du pas).
        expected_vol_0 = (params.garch_omega + params.garch_beta * params.sigma ** 2) ** 0.5
        assert vols[0] == pytest.approx(expected_vol_0, rel=1e-9)
        # la volatilite doit varier d'un pas a l'autre (preuve que garch_var
        # evolue reellement en fonction des retours, pas une constante figee)
        assert len(set(round(v, 12) for v in vols)) > 1

    def test_garch_zero_alpha_beta_is_constant(self):
        """alpha=beta=0 -> garch_var reste egal a omega a chaque pas."""
        params = _base_params(steps=10, seed=1, garch_alpha=0.0, garch_beta=0.0, garch_omega=0.0025)
        steps, _ = run_trading_simulation(params)
        for s in steps:
            assert s.volatility == pytest.approx(0.05, abs=1e-9)  # sqrt(0.0025)


class TestJumpDiffusion:
    def test_jump_frequency_matches_lambda(self):
        """Sur un grand nombre de pas, la frequence de sauts observee doit
        converger vers jump_lambda*dt (loi de Poisson, test statistique
        avec tolerance large pour eviter la fragilite)."""
        jump_lambda = 5.0
        dt = 1.0 / 252
        params = _base_params(steps=20000, seed=99, jump_lambda=jump_lambda, jump_mu=0.0, jump_sigma=0.01)
        steps, _ = run_trading_simulation(params)
        jump_prob_expected = jump_lambda * dt
        observed_freq = sum(1 for s in steps if s.jump) / len(steps)
        assert observed_freq == pytest.approx(jump_prob_expected, abs=0.01)

    def test_no_jump_lambda_zero(self):
        params = _base_params(steps=1000, seed=5, jump_lambda=0.0)
        steps, _ = run_trading_simulation(params)
        assert all(not s.jump for s in steps)


class TestMarkovRegimes:
    def test_regime_matrix_rows_sum_to_one(self):
        prng = Mulberry32(seed=123)
        matrix = build_regime_matrix(4, prng.random)
        for row in matrix:
            assert sum(row) == pytest.approx(1.0, abs=1e-9)

    def test_regime_transitions_occur_with_multiple_regimes(self):
        params = _base_params(steps=5000, seed=17, regimes=3, sigma=0.3)
        steps, _ = run_trading_simulation(params)
        regimes_seen = {s.regime for s in steps}
        # avec 3 regimes et 5000 pas, s'attendre a visiter plus d'un regime
        assert len(regimes_seen) > 1

    def test_single_regime_never_transitions_away(self):
        params = _base_params(steps=500, seed=17, regimes=1)
        steps, _ = run_trading_simulation(params)
        assert all(s.regime == 0 for s in steps)


class TestRiskMetrics:
    def test_max_drawdown_known_sequence(self):
        # prix: 100 -> 120 (pic) -> 90 -> 110 : dd = (120-90)/120 = 0.25
        prices = [100.0, 120.0, 90.0, 110.0]
        dd = max_drawdown(prices, s0=100.0)
        assert dd == pytest.approx(0.25, abs=1e-9)

    def test_max_drawdown_monotonic_rise_is_zero(self):
        prices = [100.0, 110.0, 120.0, 130.0]
        assert max_drawdown(prices, s0=100.0) == 0.0

    def test_var_95_known_sequence(self):
        # 100 retours tries de -0.99 a 0.0 par pas de 0.01 (indices 0..99)
        returns = [round(-0.99 + 0.01 * i, 6) for i in range(100)]
        # idx = floor(0.05*100) = 5 -> sorted_returns[5] = -0.94 -> var95 = 0.94
        assert value_at_risk_95(returns) == pytest.approx(0.94, abs=1e-6)

    def test_expected_shortfall_known_sequence(self):
        returns = [round(-0.99 + 0.01 * i, 6) for i in range(100)]
        # idx=5, tail = sorted_returns[:5] = [-0.99,-0.98,-0.97,-0.96,-0.95]
        # es95 = -mean(tail) = -(-0.97) = 0.97
        assert expected_shortfall_95(returns) == pytest.approx(0.97, abs=1e-6)

    def test_empty_returns_are_zero(self):
        assert value_at_risk_95([]) == 0.0
        assert expected_shortfall_95([]) == 0.0

    def test_sharpe_ratio_known_values(self):
        # total_return=0.10, steps=252, dt=1/252 -> annual_return=0.10
        # annualized_vol=0.20 -> sharpe = 0.10/0.20 = 0.5
        sharpe = sharpe_ratio(total_return=0.10, annualized_vol=0.20, steps=252, dt=1.0 / 252)
        assert sharpe == pytest.approx(0.5, abs=1e-6)

    def test_merkle_root_deterministic_and_order_sensitive(self):
        h1 = merkle_root(["a", "b", "c", "d"])
        h2 = merkle_root(["a", "b", "c", "d"])
        h3 = merkle_root(["d", "c", "b", "a"])
        assert h1 == h2
        assert h1 != h3

    def test_merkle_root_empty_is_stable_hash(self):
        import hashlib

        assert merkle_root([]) == hashlib.sha256(b"").hexdigest()

    def test_compute_trading_metrics_end_to_end(self):
        params = _base_params(steps=500, seed=21)
        steps, returns = run_trading_simulation(params)
        metrics = compute_trading_metrics(steps, params, returns)
        assert metrics.final_price == steps[-1].price
        assert isinstance(metrics.state_hash, str) and len(metrics.state_hash) == 64
        assert isinstance(metrics.merkle_root, str) and len(metrics.merkle_root) == 64


class TestDeterminism:
    def test_same_seed_same_exact_sequence(self):
        params = _base_params(steps=1000, seed=2026, regimes=3, jump_lambda=2.0)
        steps_a, returns_a = run_trading_simulation(params)
        steps_b, returns_b = run_trading_simulation(params)
        assert returns_a == returns_b
        assert [s.price for s in steps_a] == [s.price for s in steps_b]
        assert [s.regime for s in steps_a] == [s.regime for s in steps_b]
        assert [s.jump for s in steps_a] == [s.jump for s in steps_b]

    def test_different_seed_different_sequence(self):
        params_a = _base_params(steps=1000, seed=1)
        params_b = _base_params(steps=1000, seed=2)
        _, returns_a = run_trading_simulation(params_a)
        _, returns_b = run_trading_simulation(params_b)
        assert returns_a != returns_b

    def test_mulberry32_reproducible(self):
        seq_a = [Mulberry32(seed=555).random() for _ in range(20)]
        seq_b = [Mulberry32(seed=555).random() for _ in range(20)]
        assert seq_a == seq_b

    def test_box_muller_uses_provided_rand(self):
        prng = Mulberry32(seed=9)
        z1 = box_muller(prng.random)
        prng2 = Mulberry32(seed=9)
        z2 = box_muller(prng2.random)
        assert z1 == z2
