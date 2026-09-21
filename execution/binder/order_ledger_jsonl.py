"""
Append-only JSONL order ledger (chantier F6).

Provenance : porte depuis agent-trad-main (obsidia/adapters/jsonl_order_ledger.py,
PASS10), COPY_AS_IS a l'exception des imports (obsidia.domain.* -> domain.*).
Pure persistance : ce module ne decide rien, il ne fait que refuser une
double soumission deja enregistree (`submission_blocker`) — c'est la garde
d'idempotence appelee par `execution/binder/engine.py::_execute` AVANT tout
contact avec le broker.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Sequence, Union

from domain.order_ledger import OrderLedgerEvent
from domain.orders import ExecutionPlan


class JsonlOrderLedger:
    """Petit registre local durable avec garde anti-doublon par client_order_id."""

    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def append(self, event: OrderLedgerEvent) -> OrderLedgerEvent:
        events = self._read_all()
        if any(existing.event_id == event.event_id for existing in events):
            raise ValueError(f"duplicate ledger event_id: {event.event_id}")
        line = json.dumps(event.as_dict(), sort_keys=True, separators=(",", ":"))
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")
        return event

    def latest_by_client_order_id(self, client_order_id: str) -> Optional[OrderLedgerEvent]:
        matches = [e for e in self._read_all() if e.client_order_id == client_order_id]
        return matches[-1] if matches else None

    def latest_by_plan_id(self, execution_plan_id: str) -> Optional[OrderLedgerEvent]:
        matches = [e for e in self._read_all() if e.execution_plan_id == execution_plan_id]
        return matches[-1] if matches else None

    def events(self, ledger_id: Optional[str] = None) -> Sequence[OrderLedgerEvent]:
        records = self._read_all()
        if ledger_id is not None:
            records = [e for e in records if e.ledger_id == ledger_id]
        return tuple(records)

    def non_terminal(self) -> Sequence[OrderLedgerEvent]:
        latest: dict[str, OrderLedgerEvent] = {}
        for event in self._read_all():
            latest[event.ledger_id] = event
        return tuple(e for e in latest.values() if not e.is_terminal)

    def submission_blocker(self, plan: ExecutionPlan) -> Optional[str]:
        if plan.client_order_id:
            latest = self.latest_by_client_order_id(plan.client_order_id)
            if latest is not None:
                return (
                    f"client_order_id {plan.client_order_id} deja enregistre "
                    f"comme {latest.event_type.value}"
                )
        latest_plan = self.latest_by_plan_id(plan.causal_id)
        if latest_plan is not None:
            return (
                f"execution_plan_id {plan.causal_id} deja enregistre "
                f"comme {latest_plan.event_type.value}"
            )
        return None

    def verify_integrity(self) -> tuple[bool, Optional[str]]:
        try:
            self._read_all()
        except ValueError as exc:
            return False, str(exc)
        return True, None

    def _read_all(self) -> list[OrderLedgerEvent]:
        records: list[OrderLedgerEvent] = []
        seen: set[str] = set()
        for lineno, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                event = OrderLedgerEvent.from_dict(payload)
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"corrupted order ledger at line {lineno}: {exc}") from exc
            if event.event_id in seen:
                raise ValueError(f"duplicate ledger event_id: {event.event_id}")
            seen.add(event.event_id)
            records.append(event)
        return records
