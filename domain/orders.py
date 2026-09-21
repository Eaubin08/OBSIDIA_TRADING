"""
Obsidia Trading — intention, plan d'execution et consequence (chantier §14/§17).

Ce module materialise la distinction que le prototype ne faisait pas :

    DECIDER D'AGIR          -> Authority.ACT, produit par X-108
    TRADUIRE EN ORDRE       -> ExecutionPlan, produit par le planner
    ENVOYER AU BROKER       -> ExecutionResult, produit par le bridge
    CONSTATER LA CONSEQUENCE-> Fill / OrderStatus, produit par le monitoring

Un ExecutionPlan porte l'autorite qui l'a rendu possible. Le bridge d'execution
n'a aucune autorite propre : il refuse tout plan qui n'est pas porte par ACT.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional, Tuple

from domain.types import (
    ActionKind,
    Authority,
    OrderStatus,
    OrderType,
    Side,
    TimeInForce,
)


@dataclass(frozen=True)
class ExecutionPlan:
    """
    Traduction d'une decision autorisee en ordre broker concret.

    Le plan est inerte : le construire n'execute rien. Il est explicitement
    lie a l'autorite qui l'a permis (`authority`) et a la decision dont il
    decoule (`decision_id`), de sorte que le bridge puisse verifier lui-meme
    qu'il a le droit d'agir plutot que de faire confiance a son appelant.
    """

    decision_id: str
    symbol: str
    action: ActionKind
    side: Side
    quantity: float
    order_type: OrderType
    authority: Authority
    time_in_force: TimeInForce = TimeInForce.DAY
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    trail_percent: Optional[float] = None
    take_profit_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    client_order_id: Optional[str] = None
    execution_plan_id: Optional[str] = None
    reduce_only: bool = False
    rationale: str = ""

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError(
                f"un plan d'execution exige une quantite strictement positive, recu {self.quantity}"
            )
        if self.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT) and self.limit_price is None:
            raise ValueError(f"{self.order_type.value} exige un limit_price")
        if self.order_type in (OrderType.STOP, OrderType.STOP_LIMIT) and self.stop_price is None:
            raise ValueError(f"{self.order_type.value} exige un stop_price")
        if self.order_type is OrderType.TRAILING_STOP and self.trail_percent is None:
            raise ValueError("TRAILING_STOP exige un trail_percent")

    @property
    def is_authorized(self) -> bool:
        """
        Invariant central du chantier §15 : seule l'autorite ACT permet une
        action irreversible. Un plan non autorise ne doit jamais atteindre le
        broker.
        """
        if not self.action.is_irreversible:
            return True
        return self.authority.authorizes_irreversible_action

    def as_dict(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "symbol": self.symbol,
            "action": self.action.value,
            "side": self.side.value,
            "quantity": self.quantity,
            "order_type": self.order_type.value,
            "time_in_force": self.time_in_force.value,
            "authority": self.authority.value,
            "limit_price": self.limit_price,
            "stop_price": self.stop_price,
            "trail_percent": self.trail_percent,
            "take_profit_price": self.take_profit_price,
            "stop_loss_price": self.stop_loss_price,
            "client_order_id": self.client_order_id,
            "execution_plan_id": self.causal_id,
            "reduce_only": self.reduce_only,
            "rationale": self.rationale,
        }

    @property
    def causal_id(self) -> str:
        """Identifiant court et stable du plan sans dependance circulaire."""
        if self.execution_plan_id:
            return self.execution_plan_id
        payload = {
            "decision_id": self.decision_id,
            "symbol": self.symbol,
            "action": self.action.value,
            "side": self.side.value,
            "quantity": self.quantity,
            "order_type": self.order_type.value,
            "time_in_force": self.time_in_force.value,
            "authority": self.authority.value,
            "limit_price": self.limit_price,
            "stop_price": self.stop_price,
            "trail_percent": self.trail_percent,
            "take_profit_price": self.take_profit_price,
            "stop_loss_price": self.stop_loss_price,
            "client_order_id": self.client_order_id,
            "reduce_only": self.reduce_only,
            "rationale": self.rationale,
        }
        raw = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:16]

    def fingerprint(self) -> str:
        """Empreinte stable du plan, reprise dans le receipt."""
        raw = json.dumps(self.as_dict(), sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class Fill:
    """Execution partielle ou totale constatee cote broker."""

    timestamp: float
    quantity: float
    price: float
    fill_id: Optional[str] = None

    @property
    def notional(self) -> float:
        return self.quantity * self.price

    def as_dict(self) -> dict:
        return {
            "fill_id": self.fill_id,
            "timestamp": self.timestamp,
            "quantity": self.quantity,
            "price": self.price,
            "notional": self.notional,
        }


@dataclass(frozen=True)
class ExecutionResult:
    """
    Ce que le broker a reellement fait du plan.

    `submitted` a False avec un `rejected_reason` renseigne couvre les modes
    de degradation du chantier §30 : refus de gouvernance, buying power
    insuffisant, symbole invalide, broker indisponible. L'echec est toujours
    explicite — jamais un silence (contrairement a B4).
    """

    plan: ExecutionPlan
    submitted: bool
    status: OrderStatus
    broker_order_id: Optional[str] = None
    submitted_at: Optional[float] = None
    updated_at: Optional[float] = None
    filled_at: Optional[float] = None
    provider: str = ""
    mode: str = ""
    provenance: dict = field(default_factory=dict)
    fills: Tuple[Fill, ...] = field(default_factory=tuple)
    rejected_reason: Optional[str] = None

    @property
    def filled_quantity(self) -> float:
        return sum(f.quantity for f in self.fills)

    @property
    def average_fill_price(self) -> Optional[float]:
        total = self.filled_quantity
        if total <= 0:
            return None
        return sum(f.notional for f in self.fills) / total

    @property
    def is_partial(self) -> bool:
        return 0.0 < self.filled_quantity < self.plan.quantity

    @property
    def remaining_quantity(self) -> float:
        return max(0.0, self.plan.quantity - self.filled_quantity)

    @property
    def lifecycle_status(self) -> str:
        if not self.submitted:
            return "PLANNED" if self.status is OrderStatus.PENDING_SUBMIT else self.status.value
        if self.status is OrderStatus.PENDING_SUBMIT:
            return "SUBMITTED"
        if self.status is OrderStatus.ACCEPTED:
            return "ACCEPTED"
        return self.status.value

    @property
    def touched_the_market(self) -> bool:
        """Vrai des lors qu'un ordre a quitte le systeme vers le broker."""
        return self.submitted

    def as_dict(self) -> dict:
        return {
            "plan": self.plan.as_dict(),
            "plan_fingerprint": self.plan.fingerprint(),
            "execution_plan_id": self.plan.causal_id,
            "submitted": self.submitted,
            "status": self.status.value,
            "lifecycle_status": self.lifecycle_status,
            "broker_order_id": self.broker_order_id,
            "external_order_id": self.broker_order_id,
            "client_order_id": self.plan.client_order_id,
            "submitted_at": self.submitted_at,
            "updated_at": self.updated_at,
            "filled_at": self.filled_at,
            "provider": self.provider,
            "mode": self.mode,
            "provenance": self.provenance,
            "fills": [f.as_dict() for f in self.fills],
            "requested_quantity": self.plan.quantity,
            "filled_quantity": self.filled_quantity,
            "remaining_quantity": self.remaining_quantity,
            "average_fill_price": self.average_fill_price,
            "is_partial": self.is_partial,
            "rejected_reason": self.rejected_reason,
        }

    @classmethod
    def not_submitted(cls, plan: ExecutionPlan, reason: str) -> "ExecutionResult":
        """Constructeur explicite pour un plan qui n'atteint jamais le broker."""
        return cls(
            plan=plan,
            submitted=False,
            status=OrderStatus.PENDING_SUBMIT,
            rejected_reason=reason,
        )
