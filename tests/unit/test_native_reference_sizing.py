"""
Tests P1-C — Native Reference Sizing V1.

Couvre : policy fail-closed, entrees reelles requises, base de sizing,
plafonds BUY, semantique SELL (reduction de LONG uniquement), normalisation
de quantite, et frontieres d'autorite (aucun import governance/execution/
broker, purete/determinisme).
"""
import pytest

from domain.market import MarketSnapshot
from domain.portfolio import AccountState, Order, PortfolioState, Position
from domain.proposal import StrategyCandidate
from domain.types import (
    ActionKind,
    AssetClass,
    DataQuality,
    Mode,
    OrderStatus,
    OrderType,
    Provenance,
    Side,
    TimeInForce,
)
from native.sizing.native_reference_sizing import NativeReferenceSizing
from native.sizing.sizing_policy import SizingPolicy

SYMBOL = "AAPL"


def _provenance(source: str = "test") -> Provenance:
    return Provenance(source=source, fetched_at=0.0, quality=DataQuality.LIVE, mode=Mode.SIM)


def _snapshot(last_price: float = 100.0) -> MarketSnapshot:
    return MarketSnapshot(
        symbol=SYMBOL,
        asset_class=AssetClass.EQUITY,
        last_price=last_price,
        provenance=_provenance(),
    )


def _account(equity: float = 10_000.0, cash: float = 10_000.0, buying_power: float = 10_000.0) -> AccountState:
    return AccountState(equity=equity, cash=cash, buying_power=buying_power, provenance=_provenance())


def _portfolio(
    equity: float = 10_000.0,
    buying_power: float = 10_000.0,
    positions=(),
    open_orders=(),
    peak_equity=None,
) -> PortfolioState:
    return PortfolioState(
        account=_account(equity=equity, buying_power=buying_power),
        positions=tuple(positions),
        open_orders=tuple(open_orders),
        peak_equity=peak_equity,
    )


def _position(symbol: str = SYMBOL, quantity: float = 10.0, price: float = 100.0) -> Position:
    return Position(
        symbol=symbol,
        asset_class=AssetClass.EQUITY,
        quantity=quantity,
        average_entry_price=price,
        current_price=price,
    )


def _order(symbol: str, side: Side, quantity: float, filled: float = 0.0) -> Order:
    return Order(
        broker_order_id=f"o-{symbol}-{side.value}",
        symbol=symbol,
        side=side,
        quantity=quantity,
        order_type=OrderType.MARKET,
        status=OrderStatus.ACCEPTED,
        filled_quantity=filled,
    )


def _buy_candidate(symbol: str = SYMBOL, confidence: float = 0.8) -> StrategyCandidate:
    return StrategyCandidate(
        symbol=symbol,
        action=ActionKind.BUY,
        rationale="test",
        confidence=confidence,
    )


def _sell_candidate(symbol: str = SYMBOL, confidence: float = 0.8) -> StrategyCandidate:
    return StrategyCandidate(
        symbol=symbol,
        action=ActionKind.SELL,
        rationale="test",
        confidence=confidence,
    )


# ---------------------------------------------------------------------
# POLICY
# ---------------------------------------------------------------------

def test_no_policy_rejected():
    engine = NativeReferenceSizing(policy=None)
    decision = engine.size(_buy_candidate(), _snapshot(), _portfolio())
    assert decision.status == "REJECTED"
    assert decision.quantity == 0.0
    assert "SIZING_POLICY_NOT_CONFIGURED" in decision.rationale


def test_no_target_rejected():
    policy = SizingPolicy(quantity_increment=1.0)
    engine = NativeReferenceSizing(policy=policy)
    decision = engine.size(_buy_candidate(), _snapshot(), _portfolio())
    assert decision.status == "REJECTED"
    assert "SIZING_TARGET_NOT_CONFIGURED" in decision.rationale


def test_both_targets_configured_rejected_at_construction():
    with pytest.raises(ValueError):
        SizingPolicy(target_notional=1000.0, target_fraction_of_equity=0.1, quantity_increment=1.0)


def test_no_quantity_increment_rejected():
    policy = SizingPolicy(target_notional=1000.0)
    engine = NativeReferenceSizing(policy=policy)
    decision = engine.size(_buy_candidate(), _snapshot(), _portfolio())
    assert decision.status == "REJECTED"
    assert "QUANTITY_INCREMENT_NOT_CONFIGURED" in decision.rationale


def test_invalid_quantity_increment_rejected():
    policy = SizingPolicy(target_notional=1000.0, quantity_increment=0.0)
    engine = NativeReferenceSizing(policy=policy)
    decision = engine.size(_buy_candidate(), _snapshot(), _portfolio())
    assert decision.status == "REJECTED"
    assert "QUANTITY_INCREMENT_NOT_CONFIGURED" in decision.rationale


# ---------------------------------------------------------------------
# INPUTS
# ---------------------------------------------------------------------

def test_invalid_price_rejected():
    policy = SizingPolicy(target_notional=1000.0, quantity_increment=1.0)
    engine = NativeReferenceSizing(policy=policy)
    decision = engine.size(_buy_candidate(), _snapshot(last_price=0.0), _portfolio())
    assert decision.status == "REJECTED"
    assert "INVALID_MARKET_PRICE" in decision.rationale


def test_no_portfolio_rejected():
    policy = SizingPolicy(target_notional=1000.0, quantity_increment=1.0)
    engine = NativeReferenceSizing(policy=policy)
    decision = engine.size(_buy_candidate(), _snapshot(), None)
    assert decision.status == "REJECTED"
    assert "PORTFOLIO_STATE_NOT_CONFIGURED" in decision.rationale


def test_invalid_equity_rejected():
    policy = SizingPolicy(target_notional=1000.0, quantity_increment=1.0)
    engine = NativeReferenceSizing(policy=policy)
    decision = engine.size(_buy_candidate(), _snapshot(), _portfolio(equity=0.0))
    assert decision.status == "REJECTED"
    assert "INVALID_EQUITY" in decision.rationale


# ---------------------------------------------------------------------
# BASE
# ---------------------------------------------------------------------

def test_target_notional_translated_correctly():
    policy = SizingPolicy(target_notional=1000.0, quantity_increment=1.0)
    engine = NativeReferenceSizing(policy=policy)
    decision = engine.size(_buy_candidate(), _snapshot(last_price=100.0), _portfolio())
    assert decision.requested_quantity == pytest.approx(10.0)
    assert decision.quantity == pytest.approx(10.0)
    assert decision.status == "VALID"


def test_target_fraction_of_equity_translated_correctly():
    policy = SizingPolicy(target_fraction_of_equity=0.1, quantity_increment=1.0)
    engine = NativeReferenceSizing(policy=policy)
    decision = engine.size(_buy_candidate(), _snapshot(last_price=100.0), _portfolio(equity=10_000.0))
    # 10% de 10 000 = 1000 notionnel -> 10 unites a 100
    assert decision.requested_quantity == pytest.approx(10.0)
    assert decision.quantity == pytest.approx(10.0)


# ---------------------------------------------------------------------
# CAPS (BUY)
# ---------------------------------------------------------------------

def test_max_notional_cap():
    policy = SizingPolicy(target_notional=5000.0, max_notional=1000.0, quantity_increment=1.0)
    engine = NativeReferenceSizing(policy=policy)
    decision = engine.size(_buy_candidate(), _snapshot(last_price=100.0), _portfolio())
    assert decision.quantity == pytest.approx(10.0)
    assert "MAX_NOTIONAL" in decision.capped_by
    assert decision.status == "REDUCED"


def test_max_fraction_of_equity_cap():
    policy = SizingPolicy(target_notional=5000.0, max_fraction_of_equity=0.1, quantity_increment=1.0)
    engine = NativeReferenceSizing(policy=policy)
    decision = engine.size(_buy_candidate(), _snapshot(last_price=100.0), _portfolio(equity=10_000.0))
    assert decision.quantity == pytest.approx(10.0)
    assert "MAX_FRACTION_OF_EQUITY" in decision.capped_by


def test_buying_power_cap():
    policy = SizingPolicy(target_notional=5000.0, max_fraction_of_buying_power=0.2, quantity_increment=1.0)
    engine = NativeReferenceSizing(policy=policy)
    decision = engine.size(_buy_candidate(), _snapshot(last_price=100.0), _portfolio(equity=10_000.0, buying_power=5_000.0))
    # 20% de 5000 buying_power = 1000 -> 10 unites
    assert decision.quantity == pytest.approx(10.0)
    assert "MAX_FRACTION_OF_BUYING_POWER" in decision.capped_by


def test_symbol_exposure_cap():
    existing = _position(quantity=50.0, price=100.0)  # 5000 valeur, 50% equity
    policy = SizingPolicy(target_notional=5000.0, max_symbol_exposure=0.6, quantity_increment=1.0)
    engine = NativeReferenceSizing(policy=policy)
    portfolio = _portfolio(equity=10_000.0, positions=(existing,))
    decision = engine.size(_buy_candidate(), _snapshot(last_price=100.0), portfolio)
    # room = 0.6*10000 - 5000 = 1000 -> 10 unites
    assert decision.quantity == pytest.approx(10.0)
    assert "MAX_SYMBOL_EXPOSURE" in decision.capped_by


def test_gross_exposure_cap():
    existing = _position(symbol="MSFT", quantity=50.0, price=100.0)  # 5000 valeur
    policy = SizingPolicy(target_notional=5000.0, max_portfolio_gross_exposure=0.6, quantity_increment=1.0)
    engine = NativeReferenceSizing(policy=policy)
    portfolio = _portfolio(equity=10_000.0, positions=(existing,))
    decision = engine.size(_buy_candidate(), _snapshot(last_price=100.0), portfolio)
    assert decision.quantity == pytest.approx(10.0)
    assert "MAX_PORTFOLIO_GROSS_EXPOSURE" in decision.capped_by


def test_concentration_cap():
    existing = _position(quantity=50.0, price=100.0)  # 5000 valeur sur AAPL
    policy = SizingPolicy(target_notional=5000.0, max_concentration=0.6, quantity_increment=1.0)
    engine = NativeReferenceSizing(policy=policy)
    portfolio = _portfolio(equity=10_000.0, positions=(existing,))
    decision = engine.size(_buy_candidate(), _snapshot(last_price=100.0), portfolio)
    assert decision.quantity == pytest.approx(10.0)
    assert "MAX_CONCENTRATION" in decision.capped_by


def test_drawdown_blocks_new_buy_risk():
    policy = SizingPolicy(target_notional=1000.0, max_drawdown_for_new_risk=0.1, quantity_increment=1.0)
    engine = NativeReferenceSizing(policy=policy)
    portfolio = _portfolio(equity=8_000.0, peak_equity=10_000.0)  # drawdown = 0.2
    decision = engine.size(_buy_candidate(), _snapshot(last_price=100.0), portfolio)
    assert decision.status == "REJECTED"
    assert decision.quantity == 0.0
    assert "MAX_DRAWDOWN_FOR_NEW_RISK" in decision.capped_by


def test_multiple_caps_most_restrictive_wins():
    policy = SizingPolicy(
        target_notional=5000.0,
        max_notional=2000.0,
        max_fraction_of_equity=0.05,  # 5% de 10000 = 500 -> le plus restrictif
        quantity_increment=1.0,
    )
    engine = NativeReferenceSizing(policy=policy)
    decision = engine.size(_buy_candidate(), _snapshot(last_price=100.0), _portfolio(equity=10_000.0))
    assert decision.quantity == pytest.approx(5.0)
    assert "MAX_FRACTION_OF_EQUITY" in decision.capped_by
    assert "MAX_NOTIONAL" not in decision.capped_by


def test_capped_by_records_binding_constraints():
    policy = SizingPolicy(target_notional=5000.0, max_notional=1000.0, quantity_increment=1.0)
    engine = NativeReferenceSizing(policy=policy)
    decision = engine.size(_buy_candidate(), _snapshot(last_price=100.0), _portfolio())
    assert decision.capped_by
    assert decision.constraints


# ---------------------------------------------------------------------
# SELL
# ---------------------------------------------------------------------

def test_sell_with_no_long_rejected():
    policy = SizingPolicy(target_notional=1000.0, quantity_increment=1.0)
    engine = NativeReferenceSizing(policy=policy)
    decision = engine.size(_sell_candidate(), _snapshot(last_price=100.0), _portfolio())
    assert decision.status == "REJECTED"
    assert "SHORT_OPENING_UNSUPPORTED_V1" in decision.rationale
    assert decision.quantity == 0.0


def test_sell_with_existing_long_permitted():
    existing = _position(quantity=20.0, price=100.0)
    policy = SizingPolicy(target_notional=1000.0, quantity_increment=1.0)
    engine = NativeReferenceSizing(policy=policy)
    portfolio = _portfolio(equity=10_000.0, positions=(existing,))
    decision = engine.size(_sell_candidate(), _snapshot(last_price=100.0), portfolio)
    assert decision.status == "VALID"
    assert decision.quantity == pytest.approx(10.0)


def test_sell_cannot_exceed_long_position():
    existing = _position(quantity=5.0, price=100.0)
    policy = SizingPolicy(target_notional=1000.0, quantity_increment=1.0)  # demande 10
    engine = NativeReferenceSizing(policy=policy)
    portfolio = _portfolio(equity=10_000.0, positions=(existing,))
    decision = engine.size(_sell_candidate(), _snapshot(last_price=100.0), portfolio)
    assert decision.quantity == pytest.approx(5.0)
    assert decision.status == "REDUCED"
    assert "REDUCIBLE_LONG_QUANTITY" in decision.capped_by


def test_sell_open_orders_reduce_reducible_quantity():
    existing = _position(quantity=10.0, price=100.0)
    open_sell = _order(SYMBOL, Side.SELL, quantity=7.0)
    policy = SizingPolicy(target_notional=1000.0, quantity_increment=1.0)  # demande 10
    engine = NativeReferenceSizing(policy=policy)
    portfolio = _portfolio(equity=10_000.0, positions=(existing,), open_orders=(open_sell,))
    decision = engine.size(_sell_candidate(), _snapshot(last_price=100.0), portfolio)
    # reductible = 10 - 7 = 3
    assert decision.quantity == pytest.approx(3.0)
    assert "REDUCIBLE_LONG_QUANTITY" in decision.capped_by


def test_sell_cannot_open_short():
    short_position = Position(
        symbol=SYMBOL, asset_class=AssetClass.EQUITY, quantity=-10.0,
        average_entry_price=100.0, current_price=100.0,
    )
    policy = SizingPolicy(target_notional=1000.0, quantity_increment=1.0)
    engine = NativeReferenceSizing(policy=policy)
    portfolio = _portfolio(equity=10_000.0, positions=(short_position,))
    decision = engine.size(_sell_candidate(), _snapshot(last_price=100.0), portfolio)
    assert decision.status == "REJECTED"
    assert "SHORT_OPENING_UNSUPPORTED_V1" in decision.rationale


def test_high_drawdown_does_not_block_risk_reducing_sell():
    existing = _position(quantity=20.0, price=100.0)
    policy = SizingPolicy(
        target_notional=1000.0,
        max_drawdown_for_new_risk=0.05,
        quantity_increment=1.0,
    )
    engine = NativeReferenceSizing(policy=policy)
    portfolio = _portfolio(equity=8_000.0, peak_equity=10_000.0, positions=(existing,))  # drawdown 0.2
    decision = engine.size(_sell_candidate(), _snapshot(last_price=100.0), portfolio)
    assert decision.status == "VALID"
    assert decision.quantity == pytest.approx(10.0)


# ---------------------------------------------------------------------
# QUANTITY
# ---------------------------------------------------------------------

def test_quantity_increment_one():
    policy = SizingPolicy(target_notional=1037.0, quantity_increment=1.0)
    engine = NativeReferenceSizing(policy=policy)
    decision = engine.size(_buy_candidate(), _snapshot(last_price=100.0), _portfolio())
    assert decision.quantity == pytest.approx(10.0)


def test_quantity_fractional_increment():
    policy = SizingPolicy(target_notional=1037.0, quantity_increment=0.1)
    engine = NativeReferenceSizing(policy=policy)
    decision = engine.size(_buy_candidate(), _snapshot(last_price=100.0), _portfolio())
    assert decision.quantity == pytest.approx(10.3)


def test_quantity_always_rounds_downward():
    policy = SizingPolicy(target_notional=1099.0, quantity_increment=1.0)
    engine = NativeReferenceSizing(policy=policy)
    decision = engine.size(_buy_candidate(), _snapshot(last_price=100.0), _portfolio())
    assert decision.quantity == pytest.approx(10.0)
    assert decision.quantity <= decision.requested_quantity


def test_quantity_deterministic():
    policy = SizingPolicy(target_notional=1037.0, quantity_increment=0.1)
    engine = NativeReferenceSizing(policy=policy)
    d1 = engine.size(_buy_candidate(), _snapshot(last_price=100.0), _portfolio())
    d2 = engine.size(_buy_candidate(), _snapshot(last_price=100.0), _portfolio())
    assert d1.quantity == d2.quantity
    assert d1.notional == d2.notional


# ---------------------------------------------------------------------
# BOUNDARIES
# ---------------------------------------------------------------------

def test_no_authority_or_governance_import():
    import native.sizing.native_reference_sizing as module
    source = module.__file__
    with open(source, "r", encoding="utf-8") as f:
        lines = f.readlines()
    import_lines = [ln for ln in lines if ln.strip().startswith(("import ", "from "))]
    forbidden = ("governance", "execution.binder", "market.adapters", "proof", "external")
    for line in import_lines:
        for token in forbidden:
            assert token not in line, f"forbidden import found: {line!r}"


def test_same_inputs_same_decision():
    policy = SizingPolicy(target_notional=1000.0, max_notional=800.0, quantity_increment=1.0)
    engine = NativeReferenceSizing(policy=policy)
    snapshot = _snapshot(last_price=100.0)
    portfolio = _portfolio()
    d1 = engine.size(_buy_candidate(), snapshot, portfolio)
    d2 = engine.size(_buy_candidate(), snapshot, portfolio)
    assert d1 == d2
