"""Adaptation Alpaca Trading API vers BrokerPort."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from domain.orders import ExecutionPlan, ExecutionResult, Fill
from domain.portfolio import AccountState, Order, PortfolioState, Position
from domain.types import (
    AssetClass,
    DataQuality,
    Mode,
    OrderStatus,
    OrderType,
    Provenance,
    Side,
    TimeInForce,
)
from domain.ports.broker import BrokerUnavailable, UnauthorizedExecution
from domain.ports.clock import ClockPort, SystemClock
from market.adapters.alpaca.alpaca_client import AlpacaAPIError, AlpacaHTTPClient, broker_unavailable


class AlpacaBroker:
    """BrokerPort backed by Alpaca account, position and order endpoints."""

    def __init__(
        self,
        client: AlpacaHTTPClient,
        *,
        mode: Optional[Mode] = None,
        clock: Optional[ClockPort] = None,
        asset_classes: Optional[dict[str, AssetClass]] = None,
    ) -> None:
        self.client = client
        self.mode = mode or client.config.mode
        self.clock: ClockPort = clock or SystemClock()
        self.asset_classes = dict(asset_classes or {})

    def account(self) -> AccountState:
        try:
            data = self.client.trading_get("/v2/account")
        except AlpacaAPIError as exc:
            raise broker_unavailable(exc) from exc

        return AccountState(
            equity=_required_number(data, "equity"),
            cash=_required_number(data, "cash"),
            buying_power=_required_number(data, "buying_power"),
            provenance=self._provenance(),
            last_equity=_number(data, "last_equity"),
            currency=str(data.get("currency") or "USD"),
            trading_blocked=bool(data.get("trading_blocked") or data.get("account_blocked")),
            account_id=str(data.get("id")) if data.get("id") else None,
        )

    def positions(self) -> Sequence[Position]:
        try:
            data = self.client.trading_get("/v2/positions")
        except AlpacaAPIError as exc:
            raise broker_unavailable(exc) from exc
        if not isinstance(data, list):
            raise BrokerUnavailable("positions Alpaca invalides")
        return tuple(self._position_from(item) for item in data)

    def open_orders(self) -> Sequence[Order]:
        try:
            data = self.client.trading_get("/v2/orders", params={"status": "open"})
        except AlpacaAPIError as exc:
            raise broker_unavailable(exc) from exc
        if not isinstance(data, list):
            raise BrokerUnavailable("ordres ouverts Alpaca invalides")
        return tuple(self._order_from(item) for item in data)

    def portfolio(self) -> PortfolioState:
        account = self.account()
        return PortfolioState(
            account=account,
            positions=tuple(self.positions()),
            open_orders=tuple(self.open_orders()),
            peak_equity=max(account.equity, account.last_equity or account.equity),
            realized_pnl=None,
        )

    def order_status(self, broker_order_id: str) -> Optional[Order]:
        try:
            data = self.client.trading_get(f"/v2/orders/{broker_order_id}")
        except AlpacaAPIError as exc:
            message = str(exc).lower()
            if "404" in message or "not found" in message:
                return None
            raise broker_unavailable(exc) from exc
        return self._order_from(data)

    def order_by_client_order_id(self, client_order_id: str) -> Optional[Order]:
        # Lookup direct et unique : l'ancien balayage des 500 derniers ordres
        # pouvait conclure "absent" pour un ordre simplement plus ancien.
        try:
            data = self.client.trading_get(
                "/v2/orders:by_client_order_id",
                params={"client_order_id": client_order_id},
            )
        except AlpacaAPIError as exc:
            if exc.status_code == 404:
                return None
            raise broker_unavailable(exc) from exc
        if not isinstance(data, dict):
            raise BrokerUnavailable("reponse Alpaca invalide pour by_client_order_id")
        return self._order_from(data)

    def submit(self, plan: ExecutionPlan) -> ExecutionResult:
        self._require_authority(plan)
        payload = self._order_payload(plan)
        try:
            data = self.client.trading_post("/v2/orders", json_body=payload)
        except AlpacaAPIError as exc:
            if exc.is_definitive_refusal:
                return ExecutionResult(
                    plan=plan,
                    submitted=False,
                    status=OrderStatus.REJECTED,
                    rejected_reason=str(exc),
                )
            return self._resolve_ambiguous_submit(plan, exc)
        return self._execution_from(plan, data, submitted=True)

    def _resolve_ambiguous_submit(
        self, plan: ExecutionPlan, exc: AlpacaAPIError
    ) -> ExecutionResult:
        """
        Timeout / transport / 5xx : l'ordre a pu etre cree. Une relecture
        immediate par client_order_id peut lever le doute ; sinon le resultat
        reste AMBIGU. Un "introuvable" immediat ne prouve pas l'absence.
        """
        reason = f"soumission ambigue: {exc}"
        if not plan.client_order_id:
            return ExecutionResult.ambiguous(plan, reason)
        try:
            data = self.client.trading_get(
                "/v2/orders:by_client_order_id",
                params={"client_order_id": plan.client_order_id},
            )
        except AlpacaAPIError:
            return ExecutionResult.ambiguous(plan, reason)
        if not isinstance(data, dict):
            return ExecutionResult.ambiguous(plan, reason)
        return self._execution_from(plan, data, submitted=True)

    def cancel(self, plan: ExecutionPlan, broker_order_id: str) -> ExecutionResult:
        self._require_authority(plan)
        try:
            self.client.trading_delete(f"/v2/orders/{broker_order_id}")
        except AlpacaAPIError as exc:
            if exc.is_definitive_refusal:
                return ExecutionResult.not_submitted(plan, str(exc))
            return ExecutionResult.ambiguous(plan, f"annulation ambigue: {exc}")
        # Alpaca accepte la DEMANDE d'annulation : ce n'est pas une annulation
        # confirmee, des fills tardifs restent possibles.
        return ExecutionResult(
            plan=plan,
            submitted=True,
            status=OrderStatus.PENDING_CANCEL,
            broker_order_id=broker_order_id,
            submitted_at=self.clock.now(),
        )

    def replace(self, plan: ExecutionPlan, broker_order_id: str) -> ExecutionResult:
        self._require_authority(plan)
        raise NotImplementedError("replace Alpaca non implemente en PASS 3")

    def close_position(self, plan: ExecutionPlan) -> ExecutionResult:
        self._require_authority(plan)
        try:
            data = self.client.trading_delete(
                f"/v2/positions/{plan.symbol}",
                json_body={"qty": str(plan.quantity)},
            )
        except AlpacaAPIError as exc:
            if exc.is_definitive_refusal:
                return ExecutionResult.not_submitted(plan, str(exc))
            return ExecutionResult.ambiguous(plan, f"cloture ambigue: {exc}")
        return self._execution_from(plan, data, submitted=True)

    def _require_authority(self, plan: ExecutionPlan) -> None:
        if not plan.action.is_irreversible:
            raise UnauthorizedExecution(
                f"plan refuse : action {plan.action.value} n'est pas un ordre broker"
            )
        if not plan.is_authorized:
            raise UnauthorizedExecution(
                f"plan refuse : action {plan.action.value} exige ACT, "
                f"autorite portee = {plan.authority.value}"
            )

    def _order_payload(self, plan: ExecutionPlan) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "symbol": plan.symbol,
            "qty": str(plan.quantity),
            "side": plan.side.value.lower(),
            "type": _alpaca_order_type(plan.order_type),
            "time_in_force": plan.time_in_force.value.lower(),
        }
        if plan.client_order_id:
            payload["client_order_id"] = plan.client_order_id
        if plan.limit_price is not None:
            payload["limit_price"] = str(plan.limit_price)
        if plan.stop_price is not None:
            payload["stop_price"] = str(plan.stop_price)
        return payload

    def _execution_from(
        self, plan: ExecutionPlan, payload: dict[str, Any], *, submitted: bool
    ) -> ExecutionResult:
        status = _status(payload.get("status"))
        filled_qty = _number(payload, "filled_qty") or 0.0
        filled_price = _number(payload, "filled_avg_price")
        fills = ()
        if filled_qty > 0 and filled_price is not None:
            fills = (
                Fill(
                    timestamp=_timestamp(payload.get("filled_at")) or self.clock.now(),
                    quantity=filled_qty,
                    price=filled_price,
                    fill_id=str(payload.get("id")) if payload.get("id") else None,
                ),
            )
        return ExecutionResult(
            plan=plan,
            submitted=submitted,
            status=status,
            broker_order_id=str(payload.get("id")) if payload.get("id") else None,
            submitted_at=_timestamp(payload.get("submitted_at")) or self.clock.now(),
            updated_at=_timestamp(payload.get("updated_at")),
            filled_at=_timestamp(payload.get("filled_at")),
            provider="alpaca",
            mode=self.mode.value,
            provenance=self._provenance().as_dict(),
            fills=fills,
            rejected_reason=payload.get("reject_reason") or payload.get("failed_reason"),
        )

    def _position_from(self, payload: dict[str, Any]) -> Position:
        symbol = str(payload.get("symbol") or "")
        return Position(
            symbol=symbol,
            asset_class=self.asset_classes.get(symbol, _asset_class(payload)),
            quantity=_signed_qty(payload),
            average_entry_price=_required_number(payload, "avg_entry_price"),
            current_price=_number(payload, "current_price"),
            market_value=_number(payload, "market_value"),
            unrealized_pnl=_number(payload, "unrealized_pl", "unrealized_pnl"),
            realized_pnl=_number(payload, "realized_pl", "realized_pnl"),
            updated_at=self.clock.now(),
            provenance=self._provenance(),
        )

    def _order_from(self, payload: dict[str, Any]) -> Order:
        symbol = str(payload.get("symbol") or "")
        return Order(
            broker_order_id=str(payload.get("id") or ""),
            symbol=symbol,
            side=Side.BUY if str(payload.get("side")).lower() == "buy" else Side.SELL,
            quantity=_required_number(payload, "qty"),
            order_type=_order_type(payload.get("type")),
            status=_status(payload.get("status")),
            time_in_force=_time_in_force(payload.get("time_in_force")),
            filled_quantity=_number(payload, "filled_qty") or 0.0,
            average_fill_price=_number(payload, "filled_avg_price"),
            limit_price=_number(payload, "limit_price"),
            stop_price=_number(payload, "stop_price"),
            submitted_at=_timestamp(payload.get("submitted_at")),
            updated_at=_timestamp(payload.get("updated_at")),
            filled_at=_timestamp(payload.get("filled_at")),
            provider="alpaca",
            provenance=self._provenance(),
            client_order_id=payload.get("client_order_id"),
            reject_reason=payload.get("reject_reason") or payload.get("failed_reason"),
        )

    def _provenance(self) -> Provenance:
        return Provenance(
            source="alpaca",
            fetched_at=self.clock.now(),
            quality=DataQuality.LIVE,
            mode=self.mode,
        )


def _alpaca_order_type(order_type: OrderType) -> str:
    mapping = {
        OrderType.MARKET: "market",
        OrderType.LIMIT: "limit",
        OrderType.STOP: "stop",
        OrderType.STOP_LIMIT: "stop_limit",
        OrderType.TRAILING_STOP: "trailing_stop",
    }
    return mapping[order_type]


def _order_type(value: Any) -> OrderType:
    raw = str(value or "market").upper().replace("-", "_")
    return OrderType.__members__.get(raw, OrderType.MARKET)


def _time_in_force(value: Any) -> TimeInForce:
    raw = str(value or "day").upper()
    return TimeInForce.__members__.get(raw, TimeInForce.DAY)


def _status(value: Any) -> OrderStatus:
    raw = str(value or "").lower()
    if raw in ("new", "accepted", "pending_new", "accepted_for_bidding"):
        return OrderStatus.ACCEPTED
    if raw in ("partially_filled",):
        return OrderStatus.PARTIALLY_FILLED
    if raw in ("filled", "done_for_day"):
        return OrderStatus.FILLED
    if raw in ("pending_cancel",):
        # Annulation demandee, non confirmee : des fills tardifs restent possibles.
        return OrderStatus.PENDING_CANCEL
    if raw in ("canceled", "cancelled"):
        return OrderStatus.CANCELED
    if raw in ("rejected", "stopped", "suspended", "calculated"):
        return OrderStatus.REJECTED
    if raw in ("expired",):
        return OrderStatus.EXPIRED
    if raw in ("pending_submit", "pending_replace", "replaced"):
        return OrderStatus.PENDING_SUBMIT
    return OrderStatus.UNKNOWN


def _asset_class(payload: dict[str, Any]) -> AssetClass:
    raw = str(payload.get("asset_class") or "").lower()
    if "crypto" in raw:
        return AssetClass.CRYPTO
    if "option" in raw:
        return AssetClass.OPTION
    return AssetClass.EQUITY


def _signed_qty(payload: dict[str, Any]) -> float:
    qty = _number(payload, "qty") or 0.0
    side = str(payload.get("side") or "").lower()
    return -abs(qty) if side == "short" else qty


def _required_number(payload: dict[str, Any], key: str) -> float:
    value = _number(payload, key)
    if value is None:
        raise BrokerUnavailable(f"champ numerique Alpaca manquant: {key}")
    return value


def _number(payload: dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        value = payload.get(key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _timestamp(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw).astimezone(timezone.utc).timestamp()
    except ValueError:
        return None
