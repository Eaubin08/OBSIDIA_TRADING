"""Memory storage port for PASS8 append-only records."""
from __future__ import annotations

from typing import Optional, Protocol, Sequence, runtime_checkable

from domain.memory import MemoryRecord, MemoryRecordType


@runtime_checkable
class MemoryPort(Protocol):
    def append(self, record: MemoryRecord) -> MemoryRecord:
        ...

    def get(self, memory_id: str) -> Optional[MemoryRecord]:
        ...

    def query(
        self,
        *,
        cycle_id: Optional[str] = None,
        decision_id: Optional[str] = None,
        symbol: Optional[str] = None,
        record_type: Optional[MemoryRecordType] = None,
        start: Optional[float] = None,
        end: Optional[float] = None,
    ) -> Sequence[MemoryRecord]:
        ...

    def recent(self, limit: int = 10) -> Sequence[MemoryRecord]:
        ...

    def verify_integrity(self) -> tuple[bool, Optional[str]]:
        ...
