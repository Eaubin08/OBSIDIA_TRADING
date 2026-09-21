"""Order ledger storage port for durable PASS10 runtime state."""
from __future__ import annotations

from typing import Optional, Protocol, Sequence, runtime_checkable

from domain.order_ledger import OrderLedgerEvent
from domain.orders import ExecutionPlan


@runtime_checkable
class OrderLedgerPort(Protocol):
    def append(self, event: OrderLedgerEvent) -> OrderLedgerEvent:
        ...

    def latest_by_client_order_id(self, client_order_id: str) -> Optional[OrderLedgerEvent]:
        ...

    def latest_by_plan_id(self, execution_plan_id: str) -> Optional[OrderLedgerEvent]:
        ...

    def events(self, ledger_id: Optional[str] = None) -> Sequence[OrderLedgerEvent]:
        ...

    def non_terminal(self) -> Sequence[OrderLedgerEvent]:
        ...

    def submission_blocker(self, plan: ExecutionPlan) -> Optional[str]:
        ...

    def verify_integrity(self) -> tuple[bool, Optional[str]]:
        ...
