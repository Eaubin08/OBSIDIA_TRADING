"""
Obsidia Trading — surveillance post-execution (chantier §17 / §18).

Une execution n'est pas la fin du cycle. Un ordre accepte peut etre rejete,
partiellement execute, ou execute a un prix different de celui envisage. Une
position ouverte reste gouvernee : elle doit pouvoir etre conservee, reduite,
renforcee ou fermee selon l'etat reel.

Le prototype s'arretait a l'entree. Ce module ramene la consequence dans la
boucle, ou elle redevient un etat a observer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from domain.market import MarketSnapshot
from domain.orders import ExecutionResult
from domain.portfolio import Order, PortfolioState, Position
from domain.proposal import ActionProposal, Consensus, SizingDecision, StrategyCandidate
from domain.state import TradingDomainState
from domain.types import ActionKind, DataQuality, OrderStatus
from domain.ports.broker import BrokerPort, BrokerUnavailable


@dataclass(frozen=True)
class OrderObservation:
    """Ce qu'est devenu un ordre depuis sa soumission."""

    broker_order_id: str
    symbol: str
    previous_status: OrderStatus
    current_status: OrderStatus
    filled_quantity: float
    remaining_quantity: float
    average_fill_price: Optional[float]
    changed: bool
    note: str = ""
    lifecycle_status: str = ""
    provider: str = ""
    stale: bool = False
    unavailable: bool = False

    def as_dict(self) -> dict:
        return {
            "broker_order_id": self.broker_order_id,
            "symbol": self.symbol,
            "previous_status": self.previous_status.value,
            "current_status": self.current_status.value,
            "filled_quantity": self.filled_quantity,
            "remaining_quantity": self.remaining_quantity,
            "average_fill_price": self.average_fill_price,
            "changed": self.changed,
            "note": self.note,
            "lifecycle_status": self.lifecycle_status or self.current_status.value,
            "provider": self.provider,
            "stale": self.stale,
            "unavailable": self.unavailable,
        }


@dataclass(frozen=True)
class PositionReview:
    """
    Reevaluation d'une position ouverte.

    `suggested_action` est une PROPOSITION, jamais une decision : elle
    retourne dans le cycle et repasse par X-108 comme n'importe quelle autre.
    """

    symbol: str
    quantity: float
    unrealized_pnl: Optional[float]
    unrealized_pnl_pct: Optional[float]
    suggested_action: ActionKind
    reason: str
    review_id: str = ""
    position_id: str = ""
    current_state: Dict[str, object] = field(default_factory=dict)
    trigger: str = "scheduled_review"
    market_evidence: Dict[str, object] = field(default_factory=dict)
    execution_evidence: Dict[str, object] = field(default_factory=dict)
    portfolio_evidence: Dict[str, object] = field(default_factory=dict)
    risk_evidence: Dict[str, object] = field(default_factory=dict)
    confidence: float = 0.0
    provenance: Dict[str, object] = field(default_factory=dict)
    parent_decision_id: Optional[str] = None
    parent_cycle_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.position_id:
            object.__setattr__(self, "position_id", f"pos:{self.symbol}")
        if not self.review_id:
            object.__setattr__(
                self,
                "review_id",
                f"review:{self.symbol}:{self.suggested_action.value}:{self.trigger}",
            )

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "unrealized_pnl": self.unrealized_pnl,
            "unrealized_pnl_pct": self.unrealized_pnl_pct,
            "suggested_action": self.suggested_action.value,
            "reason": self.reason,
            "review_id": self.review_id,
            "position_id": self.position_id,
            "current_state": self.current_state,
            "trigger": self.trigger,
            "market_evidence": self.market_evidence,
            "execution_evidence": self.execution_evidence,
            "portfolio_evidence": self.portfolio_evidence,
            "risk_evidence": self.risk_evidence,
            "confidence": self.confidence,
            "provenance": self.provenance,
            "parent_decision_id": self.parent_decision_id,
            "parent_cycle_id": self.parent_cycle_id,
        }


@dataclass
class MonitoringReport:
    """Etat de la surveillance a l'issue d'une passe."""

    orders: List[OrderObservation] = field(default_factory=list)
    positions: List[PositionReview] = field(default_factory=list)
    reevaluation_proposals: List[ActionProposal] = field(default_factory=list)
    degraded_reasons: List[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return any(o.changed for o in self.orders)

    def as_dict(self) -> dict:
        return {
            "orders": [o.as_dict() for o in self.orders],
            "positions": [p.as_dict() for p in self.positions],
            "reevaluation_proposals": [p.as_dict() for p in self.reevaluation_proposals],
            "degraded_reasons": list(self.degraded_reasons),
            "has_changes": self.has_changes,
        }


@dataclass(frozen=True)
class MonitoringPolicy:
    """Seuils de reevaluation des positions ouvertes."""

    take_profit_pct: float = 0.10
    stop_loss_pct: float = -0.05
    reduce_above_pct: float = 0.06


class ExecutionMonitor:
    """
    Suit les ordres soumis et reevalue les positions ouvertes.

    Ne decide rien et n'execute rien : il constate et propose. Ses sorties
    reviennent dans le cycle comme des observations et des propositions,
    soumises a X-108 au meme titre que le reste.
    """

    def __init__(
        self,
        broker: BrokerPort,
        policy: Optional[MonitoringPolicy] = None,
    ) -> None:
        self.broker = broker
        self.policy = policy or MonitoringPolicy()
        self._tracked: Dict[str, OrderStatus] = {}

    def track(self, execution: Optional[ExecutionResult]) -> None:
        """Enregistre un ordre soumis pour le suivre aux cycles suivants."""
        if execution is None or not execution.submitted:
            return
        if execution.broker_order_id:
            self._tracked[execution.broker_order_id] = execution.status

    @property
    def tracked_orders(self) -> Sequence[str]:
        return tuple(self._tracked)

    def poll(
        self,
        portfolio: Optional[PortfolioState] = None,
        state: Optional[TradingDomainState] = None,
    ) -> MonitoringReport:
        """
        Interroge le broker sur les ordres suivis et reevalue les positions.

        Une indisponibilite du broker est consignee, pas levee : le cycle
        continue en etat degrade.
        """
        report = MonitoringReport()

        for order_id, previous in list(self._tracked.items()):
            try:
                order = self.broker.order_status(order_id)
            except BrokerUnavailable as exc:
                report.degraded_reasons.append(f"statut de {order_id} indisponible: {exc}")
                continue

            if order is None:
                report.degraded_reasons.append(f"ordre {order_id} inconnu du broker")
                self._tracked.pop(order_id, None)
                continue

            report.orders.append(self._observe(order, previous))
            if order.status.is_terminal:
                self._tracked.pop(order_id, None)
            else:
                self._tracked[order_id] = order.status

        if portfolio is None:
            try:
                portfolio = self.broker.portfolio()
            except BrokerUnavailable as exc:
                report.degraded_reasons.append(f"portefeuille indisponible: {exc}")
                return report

        report.positions = [
            self._review(
                p,
                portfolio=portfolio,
                snapshot=state.snapshot(p.symbol) if state else None,
            )
            for p in sorted(portfolio.positions, key=lambda p: p.symbol)
        ]
        if state is not None:
            report.reevaluation_proposals = list(
                PositionReevaluationEngine().proposals_from_reviews(report.positions, state)
            )
        return report

    def _observe(self, order: Order, previous: OrderStatus) -> OrderObservation:
        changed = order.status is not previous
        note = ""
        stale = False
        if changed:
            note = f"{previous.value} -> {order.status.value}"
            if order.status is OrderStatus.REJECTED:
                note += f" ({order.reject_reason or 'motif non fourni'})"
        elif order.is_partially_filled:
            note = "execution partielle en cours"
        elif order.status in (OrderStatus.PENDING_SUBMIT, OrderStatus.ACCEPTED):
            note = "aucune mise a jour broker"
            stale = True

        return OrderObservation(
            broker_order_id=order.broker_order_id,
            symbol=order.symbol,
            previous_status=previous,
            current_status=order.status,
            filled_quantity=order.filled_quantity,
            remaining_quantity=order.remaining_quantity,
            average_fill_price=order.average_fill_price,
            changed=changed,
            note=note,
            lifecycle_status=self._lifecycle_status(order),
            provider=order.provider,
            stale=stale,
        )

    def _review(
        self,
        position: Position,
        *,
        portfolio: PortfolioState,
        snapshot: Optional[MarketSnapshot] = None,
    ) -> PositionReview:
        """
        Propose une suite pour une position ouverte.

        Retourne KEEP par defaut : ne rien faire est une reponse pleinement
        valide, et de loin la plus frequente.
        """
        pct = position.unrealized_pnl_pct
        policy = self.policy

        trigger = "stable"
        confidence = 0.2

        if snapshot and snapshot.provenance.quality in (DataQuality.STALE, DataQuality.MISSING):
            action = ActionKind.NO_ACTION
            reason = (
                "donnee marche degradee : reevaluation irreversible impossible "
                f"({snapshot.provenance.quality.value})"
            )
            trigger = "stale_market"
            confidence = 0.0
        elif pct is None:
            action, reason = ActionKind.KEEP, "PnL latent inconnu : aucune revision fondee"
            trigger = "unknown_pnl"
        elif pct <= policy.stop_loss_pct:
            action = ActionKind.CLOSE
            reason = f"perte latente {pct:.2%} au-dela du seuil {policy.stop_loss_pct:.2%}"
            trigger = "stop_loss"
            confidence = min(1.0, abs(pct - policy.stop_loss_pct) * 8)
        elif pct >= policy.take_profit_pct:
            action = ActionKind.CLOSE
            reason = f"objectif atteint : gain latent {pct:.2%}"
            trigger = "take_profit"
            confidence = min(1.0, pct)
        elif pct >= policy.reduce_above_pct:
            action = ActionKind.REDUCE
            reason = f"gain latent {pct:.2%} : prise partielle envisageable"
            trigger = "profit_protect"
            confidence = min(0.8, pct)
        else:
            action, reason = ActionKind.KEEP, f"position dans sa plage nominale ({pct:.2%})"

        return PositionReview(
            symbol=position.symbol,
            quantity=position.quantity,
            unrealized_pnl=position.unrealized_pnl,
            unrealized_pnl_pct=pct,
            suggested_action=action,
            reason=reason,
            review_id=f"review:{position.symbol}:{action.value}:{trigger}",
            current_state=position.as_dict(),
            trigger=trigger,
            market_evidence=snapshot.as_dict() if snapshot else {},
            portfolio_evidence=portfolio.risk_metrics(),
            risk_evidence={
                "unrealized_pnl_pct": pct,
                "take_profit_pct": policy.take_profit_pct,
                "stop_loss_pct": policy.stop_loss_pct,
                "reduce_above_pct": policy.reduce_above_pct,
            },
            confidence=round(confidence, 6),
            provenance=position.provenance.as_dict() if position.provenance else {},
        )

    @staticmethod
    def _lifecycle_status(order: Order) -> str:
        if order.status is OrderStatus.PENDING_SUBMIT:
            return "PENDING"
        if order.status is OrderStatus.CANCELED:
            return "CANCELLED"
        return order.status.value


class PositionReevaluationEngine:
    """Converts position reviews into governed proposals, never broker calls."""

    def proposals_from_reviews(
        self,
        reviews: Sequence[PositionReview],
        state: TradingDomainState,
    ) -> Sequence[ActionProposal]:
        proposals: List[ActionProposal] = []
        for index, review in enumerate(sorted(reviews, key=lambda r: r.review_id)):
            action = review.suggested_action
            if action is ActionKind.KEEP:
                action = ActionKind.NO_ACTION

            snapshot = state.snapshot(review.symbol)
            price = snapshot.last_price if snapshot else 0.0
            quantity = self._quantity_for(action, review)
            notional = quantity * price if price > 0 else 0.0
            side = action.side.value if action.side else "HOLD"
            strategy = StrategyCandidate(
                symbol=review.symbol,
                action=action,
                rationale=review.reason,
                confidence=review.confidence,
                entry_price=price if price > 0 else None,
                expected_risk=(
                    abs(review.unrealized_pnl_pct)
                    if review.unrealized_pnl_pct is not None
                    else None
                ),
                provenance="position-review",
                strategy_id=f"strat:{review.review_id}:{action.value}",
                constraints=("x108_authority_required",)
                if action.is_irreversible
                else ("no_broker_order",),
                supporting_evidence=(review.trigger,),
            )
            sizing = SizingDecision(
                quantity=quantity,
                requested_quantity=quantity,
                notional=notional,
                status="VALID" if quantity > 0 else "ZERO",
                rationale=f"reevaluation issue de {review.review_id}",
            )
            proposals.append(
                ActionProposal(
                    symbol=review.symbol,
                    action=action,
                    consensus=Consensus(side=side, confidence=review.confidence),
                    sizing=sizing,
                    selected_strategy=strategy,
                    rationale=review.reason,
                    proposal_id=f"proposal:{review.review_id}",
                    candidate_rank=index,
                    portfolio_context=state.portfolio.risk_metrics()
                    if state.portfolio
                    else {},
                )
            )
        return tuple(proposals)

    @staticmethod
    def _quantity_for(action: ActionKind, review: PositionReview) -> float:
        if action is ActionKind.CLOSE:
            return abs(review.quantity)
        if action is ActionKind.REDUCE:
            return abs(review.quantity) / 2.0
        if action is ActionKind.ADD:
            return abs(review.quantity)
        return 0.0
