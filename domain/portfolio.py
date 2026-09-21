"""
Obsidia Trading — etat de compte et de portefeuille (chantier §10).

Le systeme ne raisonne jamais sur un trade isole : toute proposition est
confrontee a l'etat complet du portefeuille avant d'atteindre X-108.

Ces structures sont immuables et representent ce que le broker declare.
Elles ne recalculent pas un PnL a la place du broker : quand il le fournit,
il fait foi ; quand il ne le fournit pas, le champ reste None (chantier §30).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from domain.types import (
    AssetClass,
    OrderStatus,
    OrderType,
    Provenance,
    Side,
    TimeInForce,
)


@dataclass(frozen=True)
class Position:
    """Position ouverte telle que declaree par le broker."""

    symbol: str
    asset_class: AssetClass
    quantity: float
    average_entry_price: float
    current_price: Optional[float] = None
    market_value: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    realized_pnl: Optional[float] = None
    opened_at: Optional[float] = None
    updated_at: Optional[float] = None
    provenance: Optional[Provenance] = None

    @property
    def is_long(self) -> bool:
        return self.quantity > 0

    @property
    def is_short(self) -> bool:
        return self.quantity < 0

    @property
    def abs_quantity(self) -> float:
        return abs(self.quantity)

    @property
    def cost_basis(self) -> float:
        return abs(self.quantity) * self.average_entry_price

    @property
    def value(self) -> Optional[float]:
        """Valeur de marche : celle du broker si fournie, sinon recalculee."""
        if self.market_value is not None:
            return self.market_value
        if self.current_price is None:
            return None
        return self.quantity * self.current_price

    @property
    def unrealized_pnl_pct(self) -> Optional[float]:
        basis = self.cost_basis
        if self.unrealized_pnl is None or basis <= 0:
            return None
        return self.unrealized_pnl / basis

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "asset_class": self.asset_class.value,
            "quantity": self.quantity,
            "average_entry_price": self.average_entry_price,
            "current_price": self.current_price,
            "market_value": self.value,
            "unrealized_pnl": self.unrealized_pnl,
            "unrealized_pnl_pct": self.unrealized_pnl_pct,
            "realized_pnl": self.realized_pnl,
            "side": "LONG" if self.is_long else ("SHORT" if self.is_short else "FLAT"),
            "exposure": self.value,
            "opened_at": self.opened_at,
            "updated_at": self.updated_at,
            "provenance": self.provenance.as_dict() if self.provenance else None,
        }


@dataclass(frozen=True)
class Order:
    """Ordre connu du broker, en cours ou termine."""

    broker_order_id: str
    symbol: str
    side: Side
    quantity: float
    order_type: OrderType
    status: OrderStatus
    time_in_force: TimeInForce = TimeInForce.DAY
    filled_quantity: float = 0.0
    average_fill_price: Optional[float] = None
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    submitted_at: Optional[float] = None
    updated_at: Optional[float] = None
    filled_at: Optional[float] = None
    provider: str = ""
    provenance: Optional[Provenance] = None
    client_order_id: Optional[str] = None
    reject_reason: Optional[str] = None

    @property
    def remaining_quantity(self) -> float:
        return max(0.0, self.quantity - self.filled_quantity)

    @property
    def is_partially_filled(self) -> bool:
        return 0.0 < self.filled_quantity < self.quantity

    def as_dict(self) -> dict:
        return {
            "broker_order_id": self.broker_order_id,
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "order_type": self.order_type.value,
            "time_in_force": self.time_in_force.value,
            "status": self.status.value,
            "filled_quantity": self.filled_quantity,
            "remaining_quantity": self.remaining_quantity,
            "average_fill_price": self.average_fill_price,
            "limit_price": self.limit_price,
            "stop_price": self.stop_price,
            "submitted_at": self.submitted_at,
            "updated_at": self.updated_at,
            "filled_at": self.filled_at,
            "provider": self.provider,
            "provenance": self.provenance.as_dict() if self.provenance else None,
            "reject_reason": self.reject_reason,
        }


@dataclass(frozen=True)
class AccountState:
    """
    Etat du compte declare par le broker.

    `buying_power` est distinct de `cash` : c'est lui qui contraint reellement
    le sizing. Le prototype historique ne connaissait que le cash, ce qui rend
    B4 (achat non finance silencieusement ignore) possible.
    """

    equity: float
    cash: float
    buying_power: float
    provenance: Provenance
    last_equity: Optional[float] = None
    currency: str = "USD"
    trading_blocked: bool = False
    account_id: Optional[str] = None

    @property
    def session_pnl(self) -> Optional[float]:
        if self.last_equity is None:
            return None
        return self.equity - self.last_equity

    def as_dict(self) -> dict:
        return {
            "account_id": self.account_id,
            "equity": self.equity,
            "cash": self.cash,
            "buying_power": self.buying_power,
            "last_equity": self.last_equity,
            "session_pnl": self.session_pnl,
            "currency": self.currency,
            "trading_blocked": self.trading_blocked,
            "provenance": self.provenance.as_dict(),
        }


@dataclass(frozen=True)
class PortfolioState:
    """
    Vue consolidee : compte + positions + ordres ouverts, plus les mesures de
    risque agregees dont X-108 a besoin pour evaluer les consequences d'une
    proposition sur l'ensemble du portefeuille.
    """

    account: AccountState
    positions: Tuple[Position, ...] = field(default_factory=tuple)
    open_orders: Tuple[Order, ...] = field(default_factory=tuple)
    peak_equity: Optional[float] = None
    realized_pnl: Optional[float] = None

    def position_for(self, symbol: str) -> Optional[Position]:
        for position in self.positions:
            if position.symbol == symbol:
                return position
        return None

    def open_orders_for(self, symbol: str) -> Tuple[Order, ...]:
        return tuple(order for order in self.open_orders if order.symbol == symbol)

    @property
    def gross_exposure(self) -> float:
        """Exposition brute rapportee a l'equity. Les shorts comptent positif."""
        equity = self.account.equity
        if equity <= 0:
            return 0.0
        total = sum(abs(p.value) for p in self.positions if p.value is not None)
        return total / equity

    @property
    def net_exposure(self) -> float:
        """Exposition nette signee : les shorts compensent les longs."""
        equity = self.account.equity
        if equity <= 0:
            return 0.0
        total = sum(p.value for p in self.positions if p.value is not None)
        return total / equity

    @property
    def drawdown(self) -> float:
        """Recul depuis le pic d'equity connu, dans [0, 1]."""
        peak = self.peak_equity
        if peak is None or peak <= 0:
            return 0.0
        return max(0.0, (peak - self.account.equity) / peak)

    @property
    def concentration(self) -> float:
        """Poids de la plus grosse position rapporte a l'equity."""
        equity = self.account.equity
        if equity <= 0 or not self.positions:
            return 0.0
        values = [abs(p.value) for p in self.positions if p.value is not None]
        return (max(values) / equity) if values else 0.0

    def exposure_for(self, symbol: str) -> float:
        equity = self.account.equity
        position = self.position_for(symbol)
        if position is None or equity <= 0 or position.value is None:
            return 0.0
        return abs(position.value) / equity

    @property
    def total_unrealized_pnl(self) -> Optional[float]:
        known = [p.unrealized_pnl for p in self.positions if p.unrealized_pnl is not None]
        return sum(known) if known else None

    def risk_metrics(self) -> Dict[str, float]:
        """Bloc de mesures agregees consomme par X-108 et par le cockpit."""
        return {
            "gross_exposure": round(self.gross_exposure, 6),
            "net_exposure": round(self.net_exposure, 6),
            "drawdown": round(self.drawdown, 6),
            "concentration": round(self.concentration, 6),
            "position_count": float(len(self.positions)),
            "open_order_count": float(len(self.open_orders)),
        }

    def as_dict(self) -> dict:
        return {
            "account": self.account.as_dict(),
            "positions": [p.as_dict() for p in self.positions],
            "open_orders": [o.as_dict() for o in self.open_orders],
            "peak_equity": self.peak_equity,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.total_unrealized_pnl,
            "risk": self.risk_metrics(),
        }
