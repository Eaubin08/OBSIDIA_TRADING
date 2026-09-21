"""
apps/cockpit/demo_doubles.py — F9.

Doubles PAPER-only, deterministes, zero reseau. Meme principe et memes formes
que les doubles deja prouves en F8.5/F8.6
(tests/integration/test_end_to_end_full_stack.py) : ce ne sont pas une
nouvelle brique metier, seulement l'infrastructure de demonstration
necessaire tant qu'aucun vrai flux Alpaca live n'est branche au Cockpit.

Aucun de ces objets ne decide quoi que ce soit : DemoMarketData observe,
DemoBroker execute (ou echoue) sur ordre du Binder, DemoAggregation/
DemoStrategy/DemoSizing proposent. Seul KX108GovernanceBridge (F5) et
ExecutionPlanner (F6) — tous deux reutilises tels quels par le Cockpit,
jamais reimplementes ici — decident et autorisent.
"""
from __future__ import annotations

from typing import Callable, Optional, Sequence

from domain.market import Bar, MarketSnapshot
from domain.orders import ExecutionPlan, ExecutionResult
from domain.portfolio import AccountState, PortfolioState
from domain.proposal import Consensus, SizingDecision, StrategyCandidate
from domain.types import ActionKind, AssetClass, DataQuality, Mode, OrderStatus, OrderType, Provenance

SYMBOL = "AAPL"


def synthetic_bars(n: int = 30, base: float = 100.0) -> tuple:
    """Bougies OHLCV synthetiques mais deterministes (pas de random) — suffisant
    pour exercer le roster natif/externe sans dependre d'un flux reel."""
    out = []
    price = base
    for i in range(n):
        price = price * (1.0 + (0.001 if i % 2 == 0 else -0.0007))
        out.append(Bar(timestamp=float(i), open=price, high=price * 1.001, low=price * 0.999, close=price, volume=1_000.0))
    return tuple(out)


class DemoMarketData:
    """Observation de marche fictive. N'exprime jamais d'opinion sur une action."""

    def __init__(self, *, tradable: bool = True, market_open: bool = True, last_price: float = 100.0):
        self._tradable = tradable
        self._market_open = market_open
        self._last_price = last_price
        self._bars = synthetic_bars(base=last_price)

    def snapshot(self, symbol: str) -> MarketSnapshot:
        return self.snapshots([symbol])[symbol]

    def snapshots(self, symbols: Sequence[str]):
        return {
            s: MarketSnapshot(
                symbol=s,
                asset_class=AssetClass.EQUITY,
                last_price=self._last_price,
                provenance=Provenance(source="cockpit-demo", fetched_at=0.0, quality=DataQuality.LIVE, mode=Mode.PAPER),
                tradable=self._tradable,
                market_open=self._market_open,
                bars=self._bars,
            )
            for s in symbols
        }

    def history(self, symbol: str, limit: int = 200):
        return ()

    def context(self):
        return None


def _accepted(plan: ExecutionPlan) -> ExecutionResult:
    return ExecutionResult(
        plan=plan, submitted=True, status=OrderStatus.ACCEPTED,
        broker_order_id="cockpit-demo-order-1", mode=Mode.PAPER.value,
    )


def failing_submit(plan: ExecutionPlan) -> ExecutionResult:
    """Simule une panne broker cote soumission — jamais un succes deguise."""
    raise RuntimeError("Alpaca PAPER 500 : erreur simulee pour la demo Cockpit")


class DemoBroker:
    """
    Spy BrokerPort PAPER-only : aucun appel reseau, comportement de soumission
    injectable (`submit_behavior`) pour rejouer un succes ou un echec. Ne
    decide jamais si une action est permise — c'est le role exclusif du
    Binder (execution/binder/planner.py, F6), toujours exerce avant `submit`.
    """

    def __init__(self, *, trading_blocked: bool = False, submit_behavior: Optional[Callable] = None):
        self._trading_blocked = trading_blocked
        self._submit_behavior = submit_behavior or _accepted
        self.submit_calls = []

    def account(self) -> AccountState:
        return AccountState(
            equity=100_000.0, cash=100_000.0, buying_power=100_000.0,
            provenance=Provenance(source="cockpit-demo", fetched_at=0.0, quality=DataQuality.LIVE, mode=Mode.PAPER),
            trading_blocked=self._trading_blocked,
        )

    def positions(self):
        return ()

    def open_orders(self):
        return ()

    def portfolio(self) -> PortfolioState:
        return PortfolioState(account=self.account())

    def order_status(self, broker_order_id):
        return None

    def order_by_client_order_id(self, client_order_id):
        return None

    def submit(self, plan: ExecutionPlan) -> ExecutionResult:
        self.submit_calls.append(plan)
        return self._submit_behavior(plan)

    def cancel(self, plan, broker_order_id):
        raise NotImplementedError

    def replace(self, plan, broker_order_id):
        raise NotImplementedError

    def close_position(self, plan):
        raise NotImplementedError


class DemoAggregation:
    """Agrege les votes des agents en un Consensus. Ne decide jamais ACT/HOLD/BLOCK."""

    def aggregate(self, outputs):
        return Consensus(side="BUY", confidence=0.75)


class DemoStrategy:
    """Propose UNE candidature. Une proposition n'est pas une decision (Intent != Action)."""

    def build(self, symbol, snapshot, consensus, portfolio, opportunities=()):
        return (
            StrategyCandidate(
                symbol=symbol, action=ActionKind.BUY, rationale="Cockpit F9 — scenario demo",
                confidence=0.75, order_type=OrderType.MARKET, strategy_id="cockpit-demo-strategy",
            ),
        )


class DemoSizing:
    """Dimensionne la quantite proposee. Ne decide jamais si l'action est permise."""

    def size(self, candidate, snapshot, portfolio):
        return SizingDecision(quantity=1.0, requested_quantity=1.0)
