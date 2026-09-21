"""Canonical memory, experience and replay value objects for PASS8."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from domain.receipt import canonical_json

MEMORY_SCHEMA_VERSION = "memory.v1"
EXPERIENCE_SCHEMA_VERSION = "experience.v1"
REPLAY_SCHEMA_VERSION = "replay.v1"


class MemoryRecordType(str, Enum):
    OBSERVATION = "OBSERVATION"
    DECISION = "DECISION"
    EXECUTION = "EXECUTION"
    CONSEQUENCE = "CONSEQUENCE"
    REVIEW = "REVIEW"
    SYSTEM_EVENT = "SYSTEM_EVENT"


class IntegrityStatus(str, Enum):
    OK = "OK"
    CORRUPTED = "CORRUPTED"
    UNKNOWN = "UNKNOWN"


class ConsequenceState(str, Enum):
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    COMPLETE = "COMPLETE"


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    record_type: MemoryRecordType
    cycle_id: str
    timestamp: float
    payload: Dict[str, Any] = field(default_factory=dict)
    parent_cycle_id: Optional[str] = None
    decision_id: Optional[str] = None
    symbol: Optional[str] = None
    provenance: Dict[str, Any] = field(default_factory=dict)
    receipt_hash: Optional[str] = None
    integrity_status: IntegrityStatus = IntegrityStatus.OK
    memory_schema_version: str = MEMORY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.memory_schema_version != MEMORY_SCHEMA_VERSION:
            raise ValueError(f"unknown memory schema version: {self.memory_schema_version}")

    def content_for_hash(self) -> dict:
        return {
            "memory_schema_version": self.memory_schema_version,
            "memory_id": self.memory_id,
            "record_type": self.record_type.value,
            "cycle_id": self.cycle_id,
            "parent_cycle_id": self.parent_cycle_id,
            "decision_id": self.decision_id,
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "provenance": self.provenance,
            "receipt_hash": self.receipt_hash,
            "integrity_status": self.integrity_status.value,
        }

    def integrity_hash(self) -> str:
        raw = canonical_json(self.content_for_hash()).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def as_dict(self) -> dict:
        payload = self.content_for_hash()
        payload["integrity_hash"] = self.integrity_hash()
        return payload

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "MemoryRecord":
        expected = payload.get("integrity_hash")
        record = cls(
            memory_id=str(payload["memory_id"]),
            record_type=MemoryRecordType(payload["record_type"]),
            cycle_id=str(payload["cycle_id"]),
            parent_cycle_id=payload.get("parent_cycle_id"),
            decision_id=payload.get("decision_id"),
            symbol=payload.get("symbol"),
            timestamp=float(payload["timestamp"]),
            payload=dict(payload.get("payload") or {}),
            provenance=dict(payload.get("provenance") or {}),
            receipt_hash=payload.get("receipt_hash"),
            integrity_status=IntegrityStatus(payload.get("integrity_status", "OK")),
            memory_schema_version=str(payload.get("memory_schema_version", "")),
        )
        if expected and expected != record.integrity_hash():
            raise ValueError(f"corrupted memory record: {record.memory_id}")
        return record


@dataclass(frozen=True)
class ExperienceRecord:
    experience_id: str
    cycle_id: str
    decision_id: str
    proposal_id: str
    symbol: str
    action: str
    authority: str
    consequence_state: ConsequenceState
    timestamp: float
    execution_plan_id: Optional[str] = None
    execution_status: Optional[str] = None
    broker_order_id: Optional[str] = None
    position_review_id: Optional[str] = None
    reevaluation_proposal_id: Optional[str] = None
    receipt_hash: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    consequence: Dict[str, Any] = field(default_factory=dict)
    experience_schema_version: str = EXPERIENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.experience_schema_version != EXPERIENCE_SCHEMA_VERSION:
            raise ValueError(
                f"unknown experience schema version: {self.experience_schema_version}"
            )

    def as_dict(self) -> dict:
        return {
            "experience_schema_version": self.experience_schema_version,
            "experience_id": self.experience_id,
            "cycle_id": self.cycle_id,
            "decision_id": self.decision_id,
            "proposal_id": self.proposal_id,
            "symbol": self.symbol,
            "action": self.action,
            "authority": self.authority,
            "execution_plan_id": self.execution_plan_id,
            "execution_status": self.execution_status,
            "broker_order_id": self.broker_order_id,
            "position_review_id": self.position_review_id,
            "reevaluation_proposal_id": self.reevaluation_proposal_id,
            "receipt_hash": self.receipt_hash,
            "consequence_state": self.consequence_state.value,
            "timestamp": self.timestamp,
            "context": self.context,
            "consequence": self.consequence,
        }

    @classmethod
    def from_cycle(
        cls,
        *,
        cycle_id: str,
        decision_id: str,
        proposal_id: str,
        symbol: str,
        action: str,
        authority: str,
        timestamp: float,
        receipt_hash: Optional[str] = None,
        execution_plan_id: Optional[str] = None,
        execution_status: Optional[str] = None,
        broker_order_id: Optional[str] = None,
        consequence: Optional[Dict[str, Any]] = None,
        position_review_id: Optional[str] = None,
        reevaluation_proposal_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> "ExperienceRecord":
        consequence_payload = dict(consequence or {})
        state = _consequence_state(consequence_payload, execution_status)
        return cls(
            experience_id=f"exp:{cycle_id}:{decision_id}",
            cycle_id=cycle_id,
            decision_id=decision_id,
            proposal_id=proposal_id,
            symbol=symbol,
            action=action,
            authority=authority,
            execution_plan_id=execution_plan_id,
            execution_status=execution_status,
            broker_order_id=broker_order_id,
            position_review_id=position_review_id,
            reevaluation_proposal_id=reevaluation_proposal_id,
            receipt_hash=receipt_hash,
            consequence_state=state,
            timestamp=timestamp,
            context=dict(context or {}),
            consequence=consequence_payload,
        )


def _consequence_state(
    consequence: Dict[str, Any], execution_status: Optional[str]
) -> ConsequenceState:
    if consequence.get("is_partial") or execution_status == "PARTIALLY_FILLED":
        return ConsequenceState.PARTIAL
    if consequence.get("executed") is False and not execution_status:
        return ConsequenceState.PENDING
    if execution_status in {"FILLED", "REJECTED", "CANCELED", "CANCELLED", "EXPIRED"}:
        return ConsequenceState.COMPLETE
    return ConsequenceState.PENDING
