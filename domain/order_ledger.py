"""Durable order ledger value objects for PASS10."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from domain.orders import ExecutionPlan, ExecutionResult
from domain.receipt import canonical_json
from domain.types import Mode, OrderStatus

ORDER_LEDGER_SCHEMA_VERSION = "order_ledger.v1"


class OrderLedgerEventType(str, Enum):
    PLANNED = "PLANNED"
    SUBMISSION_INTENT_RECORDED = "SUBMISSION_INTENT_RECORDED"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


ACTIVE_LEDGER_EVENTS = {
    OrderLedgerEventType.SUBMISSION_INTENT_RECORDED,
    OrderLedgerEventType.SUBMITTED,
    OrderLedgerEventType.ACKNOWLEDGED,
    OrderLedgerEventType.PARTIAL,
    OrderLedgerEventType.UNKNOWN,
    OrderLedgerEventType.RECOVERY_REQUIRED,
    OrderLedgerEventType.RECONCILIATION_REQUIRED,
}

TERMINAL_LEDGER_EVENTS = {
    OrderLedgerEventType.FILLED,
    OrderLedgerEventType.REJECTED,
    OrderLedgerEventType.CANCELLED,
}


@dataclass(frozen=True)
class OrderLedgerEvent:
    ledger_id: str
    event_id: str
    event_type: OrderLedgerEventType
    timestamp: float
    cycle_id: Optional[str] = None
    decision_id: Optional[str] = None
    execution_plan_id: Optional[str] = None
    client_order_id: Optional[str] = None
    external_order_id: Optional[str] = None
    symbol: Optional[str] = None
    status: Optional[str] = None
    mode: Optional[str] = None
    provider: Optional[str] = None
    receipt_hash: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    order_ledger_schema_version: str = ORDER_LEDGER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.order_ledger_schema_version != ORDER_LEDGER_SCHEMA_VERSION:
            raise ValueError(
                f"unknown order ledger schema version: {self.order_ledger_schema_version}"
            )

    @property
    def is_terminal(self) -> bool:
        return self.event_type in TERMINAL_LEDGER_EVENTS

    @property
    def blocks_submission(self) -> bool:
        return self.event_type in ACTIVE_LEDGER_EVENTS

    def content_for_hash(self) -> dict:
        return {
            "order_ledger_schema_version": self.order_ledger_schema_version,
            "ledger_id": self.ledger_id,
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "cycle_id": self.cycle_id,
            "decision_id": self.decision_id,
            "execution_plan_id": self.execution_plan_id,
            "client_order_id": self.client_order_id,
            "external_order_id": self.external_order_id,
            "symbol": self.symbol,
            "status": self.status,
            "mode": self.mode,
            "provider": self.provider,
            "receipt_hash": self.receipt_hash,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }

    def integrity_hash(self) -> str:
        raw = canonical_json(self.content_for_hash()).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def as_dict(self) -> dict:
        payload = self.content_for_hash()
        payload["integrity_hash"] = self.integrity_hash()
        return payload

    @classmethod
    def from_plan(
        cls,
        *,
        event_type: OrderLedgerEventType,
        cycle_id: str,
        plan: ExecutionPlan,
        timestamp: float,
        mode: Mode,
        provider: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> "OrderLedgerEvent":
        ledger_id = f"order:{plan.causal_id}"
        return cls(
            ledger_id=ledger_id,
            event_id=_event_id(ledger_id, event_type, timestamp),
            event_type=event_type,
            timestamp=timestamp,
            cycle_id=cycle_id,
            decision_id=plan.decision_id,
            execution_plan_id=plan.causal_id,
            client_order_id=plan.client_order_id,
            symbol=plan.symbol,
            status=event_type.value,
            mode=mode.value,
            provider=provider,
            payload=dict(payload or {"plan": plan.as_dict()}),
        )

    @classmethod
    def from_result(
        cls,
        *,
        cycle_id: str,
        result: ExecutionResult,
        timestamp: float,
        mode: Mode,
        receipt_hash: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> "OrderLedgerEvent":
        event_type = event_type_from_order_status(result.status, result.submitted)
        plan = result.plan
        ledger_id = f"order:{plan.causal_id}"
        return cls(
            ledger_id=ledger_id,
            event_id=_event_id(ledger_id, event_type, timestamp),
            event_type=event_type,
            timestamp=timestamp,
            cycle_id=cycle_id,
            decision_id=plan.decision_id,
            execution_plan_id=plan.causal_id,
            client_order_id=plan.client_order_id,
            external_order_id=result.broker_order_id,
            symbol=plan.symbol,
            status=result.status.value,
            mode=mode.value,
            provider=result.provider,
            receipt_hash=receipt_hash,
            payload=dict(payload or {"execution": result.as_dict()}),
        )

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "OrderLedgerEvent":
        expected = payload.get("integrity_hash")
        event = cls(
            ledger_id=str(payload["ledger_id"]),
            event_id=str(payload["event_id"]),
            event_type=OrderLedgerEventType(payload["event_type"]),
            timestamp=float(payload["timestamp"]),
            cycle_id=payload.get("cycle_id"),
            decision_id=payload.get("decision_id"),
            execution_plan_id=payload.get("execution_plan_id"),
            client_order_id=payload.get("client_order_id"),
            external_order_id=payload.get("external_order_id"),
            symbol=payload.get("symbol"),
            status=payload.get("status"),
            mode=payload.get("mode"),
            provider=payload.get("provider"),
            receipt_hash=payload.get("receipt_hash"),
            payload=dict(payload.get("payload") or {}),
            order_ledger_schema_version=str(
                payload.get("order_ledger_schema_version", "")
            ),
        )
        if expected and expected != event.integrity_hash():
            raise ValueError(f"corrupted order ledger event: {event.event_id}")
        return event


def event_type_from_order_status(
    status: OrderStatus, submitted: bool = True
) -> OrderLedgerEventType:
    if not submitted:
        if status is OrderStatus.REJECTED:
            return OrderLedgerEventType.REJECTED
        return OrderLedgerEventType.UNKNOWN
    if status is OrderStatus.ACCEPTED:
        return OrderLedgerEventType.ACKNOWLEDGED
    if status is OrderStatus.PARTIALLY_FILLED:
        return OrderLedgerEventType.PARTIAL
    if status is OrderStatus.FILLED:
        return OrderLedgerEventType.FILLED
    if status is OrderStatus.CANCELED:
        return OrderLedgerEventType.CANCELLED
    if status in (OrderStatus.REJECTED, OrderStatus.EXPIRED):
        return OrderLedgerEventType.REJECTED
    if status is OrderStatus.PENDING_SUBMIT:
        return OrderLedgerEventType.SUBMITTED
    return OrderLedgerEventType.UNKNOWN


def _event_id(
    ledger_id: str, event_type: OrderLedgerEventType, timestamp: float
) -> str:
    seed = f"{ledger_id}:{event_type.value}:{timestamp:.9f}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
