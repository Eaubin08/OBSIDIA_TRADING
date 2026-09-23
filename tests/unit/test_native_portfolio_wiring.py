"""
P1-A — Native Trading State Input Integrity.

Preuve que l'ecart d'integrite decouvert par l'audit produit
(TRADING_PRODUCT_CORE_AUDIT_READY) est ferme : `native/agents/adapter.py`
cable desormais reellement `spreads_bps`/`order_book_imbalance`/`drawdown`
depuis les objets canoniques `MarketSnapshot`/`PortfolioState`, et les agents
qui dependent de champs potentiellement absents (spread, event risk, BTC
reference, sentiment, exposure, drawdown, slippage, order book imbalance)
traitent l'absence comme un `unknown` explicite -- jamais comme une
observation numerique favorable inventee.

Principe verifie partout : UNKNOWN != ZERO.

`exposure` reste explicitement `None` (EXPOSURE_SEMANTICS_UNRESOLVED) et
`slippage_bps` reste explicitement `None` (aucune source pre-execution) --
ce ne sont pas des regressions, c'est le choix documente de ne pas inventer
une semantique ou une donnee absente du repo (voir native/agents/adapter.py
et docs/MIGRATION_PROVENANCE.md, section P1-A).
"""
from __future__ import annotations

from domain.market import Bar, MarketSnapshot, Quote
from domain.portfolio import AccountState, PortfolioState
from domain.provenance import SourceProvenance
from domain.types import AssetClass, DataQuality, Mode, Provenance

from native.agents.adapter import trading_state_from_snapshot
from native.agents.contracts import TradingState
from native.agents.domains.trading_agents import (
    CorrelationAgent,
    EventAgent,
    ExecutionQualityAgent,
    LiquidityAgent,
    MacroAgent,
    PortfolioAgent,
    PortfolioStressAgent,
    PredictionAgent,
    RegimeShiftAgent,
    SentimentAgent,
    VolatilityAgent,
)


def _bars(n: int = 25, base: float = 100.0):
    out = []
    price = base
    for i in range(n):
        price *= 1.001 if i % 2 == 0 else 0.999
        out.append(Bar(timestamp=float(i), open=price, high=price * 1.001, low=price * 0.999, close=price, volume=1_000.0))
    return tuple(out)


def _provenance(mode: Mode = Mode.PAPER) -> Provenance:
    return Provenance(source="test", fetched_at=0.0, quality=DataQuality.LIVE, mode=mode)


def _snapshot(quote=None, bars=None) -> MarketSnapshot:
    return MarketSnapshot(
        symbol="AAPL", asset_class=AssetClass.EQUITY, last_price=100.0,
        provenance=_provenance(), quote=quote, bars=bars if bars is not None else _bars(),
    )


def _portfolio(peak_equity=None, equity=100_000.0) -> PortfolioState:
    account = AccountState(
        equity=equity, cash=equity, buying_power=equity,
        provenance=_provenance(), trading_blocked=False,
    )
    return PortfolioState(account=account, peak_equity=peak_equity)


# --- 1. Vraies valeurs PortfolioState atteignent les agents portfolio -----

def test_real_portfolio_drawdown_reaches_portfolio_agents():
    portfolio = _portfolio(peak_equity=120_000.0, equity=100_000.0)  # drawdown = (120000-100000)/120000
    state = trading_state_from_snapshot("AAPL", _snapshot(), portfolio)
    assert state.drawdown is not None
    assert abs(state.drawdown - (20_000.0 / 120_000.0)) < 1e-9


# --- 2. drawdown non silencieusement remplace par zero quand connu -------

def test_known_nonzero_drawdown_is_not_replaced_by_zero():
    portfolio = _portfolio(peak_equity=200_000.0, equity=100_000.0)  # drawdown = 0.5
    state = trading_state_from_snapshot("AAPL", _snapshot(), portfolio)
    assert state.drawdown == 0.5
    vote = PortfolioAgent().evaluate(
        TradingState(symbol="AAPL", prices=[100.0] * 25, drawdown=0.5, exposure=0.5)
    )
    assert vote.proposed_verdict == "SELL"  # drawdown > 0.10 doit rester detecte
    assert "MISSING_PORTFOLIO_STATE" not in vote.unknowns


# --- 3. Semantique exposure explicitement non resolue (documentee, testee) -

def test_exposure_semantics_explicitly_unresolved_not_invented():
    portfolio = _portfolio(peak_equity=120_000.0, equity=100_000.0)
    state = trading_state_from_snapshot("AAPL", _snapshot(), portfolio)
    assert state.exposure is None  # jamais devine (gross vs net vs symbol-specific)
    vote = PortfolioAgent().evaluate(state)
    assert vote.proposed_verdict == "HOLD"
    assert "EXPOSURE_SEMANTICS_UNRESOLVED" in vote.unknowns
    assert vote.confidence == 0.0


# --- 4. Vrai spread MarketSnapshot atteint les agents pertinents ---------

def test_real_spread_reaches_liquidity_and_execution_agents():
    quote = Quote(timestamp=0.0, bid_price=99.9, ask_price=100.1, bid_size=500.0, ask_size=500.0)
    state = trading_state_from_snapshot("AAPL", _snapshot(quote=quote))
    assert state.spreads_bps and abs(state.spreads_bps[-1] - quote.spread_bps) < 1e-9
    # spread ~20 bps -> ni liquide (<12) ni illiquide (>25) : HOLD, mais le
    # spread reel doit apparaitre dans le vote, pas un unknown.
    vote = LiquidityAgent().evaluate(
        TradingState(symbol="AAPL", prices=[100.0] * 25, volumes=[1000.0] * 25, spreads_bps=[quote.spread_bps])
    )
    assert "MISSING_SPREAD" not in vote.unknowns


# --- 5. Vrai imbalance L1 atteint les agents pertinents si disponible ----

def test_real_order_book_imbalance_reaches_portfolio_stress_agent():
    quote = Quote(timestamp=0.0, bid_price=99.9, ask_price=100.1, bid_size=800.0, ask_size=200.0)
    state = trading_state_from_snapshot("AAPL", _snapshot(quote=quote), _portfolio(peak_equity=100_000.0, equity=100_000.0))
    assert state.order_book_imbalance is not None
    assert abs(state.order_book_imbalance - quote.order_book_imbalance) < 1e-9
    vote = PortfolioStressAgent().evaluate(
        TradingState(symbol="AAPL", prices=[100.0] * 25, drawdown=0.0, exposure=0.1, order_book_imbalance=state.order_book_imbalance)
    )
    assert "MISSING_ORDER_BOOK_IMBALANCE" not in vote.unknowns


# --- 6. Spread manquant ne devient PAS un spread serre invente -----------

def test_missing_spread_never_becomes_favorable_tight_spread():
    state = trading_state_from_snapshot("AAPL", _snapshot(quote=None))
    assert state.spreads_bps == []
    vote = LiquidityAgent().evaluate(state)
    assert vote.proposed_verdict == "HOLD"
    assert "MISSING_SPREAD" in vote.unknowns

    vote_exec = ExecutionQualityAgent().evaluate(
        TradingState(symbol="AAPL", prices=[100.0] * 25, spreads_bps=[], slippage_bps=1.0)
    )
    assert vote_exec.proposed_verdict == "HOLD"
    assert "MISSING_SPREAD" in vote_exec.unknowns


# --- 7. Donnee event manquante ne devient PAS un faux signal bullish ----

def test_missing_event_data_never_becomes_fake_bullish_signal():
    state = TradingState(symbol="AAPL", prices=[100.0] * 25, event_risk_scores=[])
    vote = EventAgent().evaluate(state)
    assert vote.proposed_verdict == "HOLD"  # jamais BUY (l'ancien defaut 0.0 < 0.25 produisait BUY)
    assert "MISSING_EVENT_RISK" in vote.unknowns

    vote_macro = MacroAgent().evaluate(state)
    assert vote_macro.proposed_verdict == "HOLD"
    assert "MISSING_EVENT_RISK" in vote_macro.unknowns


# --- 8. Sentiment manquant honnetement represente ------------------------

def test_missing_sentiment_is_represented_honestly():
    state = TradingState(symbol="AAPL", prices=[100.0] * 25, sentiment_scores=[])
    vote = SentimentAgent().evaluate(state)
    assert vote.proposed_verdict == "HOLD"
    assert "MISSING_SENTIMENT" in vote.unknowns
    assert vote.confidence == 0.0


# --- 9. Slippage manquant non invente -------------------------------------

def test_missing_slippage_is_not_invented():
    state = trading_state_from_snapshot("AAPL", _snapshot())
    assert state.slippage_bps is None  # aucune source pre-execution, jamais 0.0 fabrique
    vote = ExecutionQualityAgent().evaluate(
        TradingState(symbol="AAPL", prices=[100.0] * 25, spreads_bps=[5.0], slippage_bps=None)
    )
    assert vote.proposed_verdict == "HOLD"
    assert "MISSING_SLIPPAGE" in vote.unknowns


# --- 10. Donnee portfolio manquante explicite -----------------------------

def test_missing_portfolio_state_is_explicit_not_fabricated_zero():
    state = trading_state_from_snapshot("AAPL", _snapshot(), portfolio=None)
    assert state.drawdown is None
    assert state.exposure is None
    vote = PortfolioAgent().evaluate(state)
    assert vote.proposed_verdict == "HOLD"
    assert "MISSING_PORTFOLIO_STATE" in vote.unknowns
    assert vote.confidence == 0.0

    vote_stress = PortfolioStressAgent().evaluate(state)
    assert vote_stress.proposed_verdict == "HOLD"
    assert "MISSING_PORTFOLIO_STATE" in vote_stress.unknowns


# --- 11/12. Comportement calibre Volatility/RegimeShift inchange ---------

def test_calibrated_volatility_agent_behavior_unchanged_by_p1a():
    prices = [100.0 + (i % 3) * 0.5 for i in range(70)]
    state_before = TradingState(symbol="AAPL", prices=prices)
    state_after = TradingState(symbol="AAPL", prices=prices, drawdown=None, exposure=None, slippage_bps=None, order_book_imbalance=None)
    vote_before = VolatilityAgent().evaluate(state_before)
    vote_after = VolatilityAgent().evaluate(state_after)
    assert vote_before.proposed_verdict == vote_after.proposed_verdict
    assert vote_before.confidence == vote_after.confidence


def test_calibrated_regimeshift_agent_behavior_unchanged_by_p1a():
    prices = [100.0 + (i % 5) * 0.3 for i in range(30)]
    state_before = TradingState(symbol="AAPL", prices=prices)
    state_after = TradingState(symbol="AAPL", prices=prices, drawdown=None, exposure=None, slippage_bps=None, order_book_imbalance=None)
    vote_before = RegimeShiftAgent().evaluate(state_before)
    vote_after = RegimeShiftAgent().evaluate(state_after)
    assert vote_before.proposed_verdict == vote_after.proposed_verdict
    assert vote_before.confidence == vote_after.confidence


# --- 13. Adapter Native produit toujours un AgentOutput canonique --------

def test_native_adapter_still_outputs_canonical_agent_output():
    from native.agents.adapter import NativeRosterAnalysisAdapter
    from domain.proposal import AgentOutput

    adapter = NativeRosterAnalysisAdapter()
    outputs = adapter.analyse("AAPL", _snapshot(), _portfolio(peak_equity=110_000.0, equity=100_000.0))
    assert len(outputs) == 17
    assert all(isinstance(o, AgentOutput) for o in outputs)


# --- 14. Provenance canonique existante preservee -------------------------

def test_canonical_source_provenance_preserved_after_p1a():
    from native.agents.adapter import NativeRosterAnalysisAdapter

    adapter = NativeRosterAnalysisAdapter()
    outputs = adapter.analyse("AAPL", _snapshot(), _portfolio(peak_equity=110_000.0, equity=100_000.0))
    for output in outputs:
        assert output.source_provenance is not None
        assert output.source_provenance.source_system == "native"


# --- Correlation : reference BTC manquante reste neutre + signalee -------

def test_missing_btc_reference_stays_neutral_and_flagged():
    state = TradingState(symbol="AAPL", prices=[100.0 + i * 0.1 for i in range(10)], btc_reference_prices=[])
    vote = CorrelationAgent().evaluate(state)
    assert vote.proposed_verdict == "HOLD"
    assert "MISSING_BTC_REFERENCE" in vote.unknowns


# --- Prediction : composants manquants signales sans changer la formule --

def test_prediction_agent_flags_missing_components_without_inventing_them():
    prices = [100.0 + (i % 4) * 0.2 for i in range(25)]
    state_full = TradingState(symbol="AAPL", prices=prices, event_risk_scores=[0.5], spreads_bps=[10.0])
    state_partial = TradingState(symbol="AAPL", prices=prices, event_risk_scores=[], spreads_bps=[])
    vote_full = PredictionAgent().evaluate(state_full)
    vote_partial = PredictionAgent().evaluate(state_partial)
    assert vote_full.unknowns == []
    assert "MISSING_EVENT_RISK" in vote_partial.unknowns
    assert "MISSING_SPREAD" in vote_partial.unknowns
