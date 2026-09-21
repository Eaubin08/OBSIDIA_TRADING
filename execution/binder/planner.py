"""
Obsidia Trading — planification d'execution (chantier §14).

Entre « decider d'agir » et « envoyer un ordre au broker » il manque une
etape que le prototype n'avait pas : traduire une decision autorisee en un
ordre concret, verifiable avant depart.

Le planner est la seule piece autorisee a fabriquer un ExecutionPlan, et il
refuse de le faire des que l'autorite ne le permet pas. C'est la premiere des
deux barrieres du chantier §15 ; la seconde est dans le bridge lui-meme.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from domain.orders import ExecutionPlan
from domain.receipt import Decision
from domain.state import TradingDomainState
from domain.types import ActionKind, OrderType, TimeInForce


@dataclass(frozen=True)
class PlannerPolicy:
    """Preferences de traduction decision -> ordre."""

    default_order_type: OrderType = OrderType.MARKET
    time_in_force: TimeInForce = TimeInForce.DAY
    limit_slippage_bps: float = 5.0
    attach_protective_orders: bool = True


class ExecutionPlanner:
    """
    Traduit une decision en plan d'execution, ou en rien du tout.

    Retourne None dans tous les cas ou aucun ordre ne doit partir :
      - l'autorite n'est pas ACT ;
      - l'action n'est pas irreversible (WAIT, KEEP, NO_ACTION) ;
      - la taille est nulle ou refusee ;
      - l'etat du domaine ne supporte pas une action irreversible.

    Un None n'est jamais un echec silencieux : le moteur consigne la raison
    dans le receipt.
    """

    def __init__(self, policy: Optional[PlannerPolicy] = None) -> None:
        self.policy = policy or PlannerPolicy()

    def plan(
        self, decision: Decision, state: TradingDomainState
    ) -> Optional[ExecutionPlan]:
        proposal = decision.proposal

        # ── Barriere de gouvernance ───────────────────────────────────────
        if not decision.authorizes_action:
            return None
        if not proposal.action.is_irreversible:
            return None

        # ── Barriere de faisabilite ───────────────────────────────────────
        quantity = proposal.sizing.quantity
        if quantity <= 0:
            return None

        supported, _ = state.can_support_irreversible_action(proposal.symbol)
        if not supported:
            return None

        snapshot = state.snapshot(proposal.symbol)
        if snapshot is None:
            return None

        side = proposal.side
        if side is None:
            return None

        strategy = proposal.selected_strategy
        order_type = strategy.order_type if strategy else self.policy.default_order_type

        limit_price = self._limit_price(order_type, snapshot.last_price, proposal.action)
        stop_price = strategy.stop_loss if (strategy and order_type in (
            OrderType.STOP, OrderType.STOP_LIMIT)) else None

        take_profit = None
        stop_loss = None
        if self.policy.attach_protective_orders and strategy is not None:
            take_profit = strategy.take_profit
            stop_loss = strategy.stop_loss

        return ExecutionPlan(
            decision_id=decision.decision_id,
            symbol=proposal.symbol,
            action=proposal.action,
            side=side,
            quantity=quantity,
            order_type=order_type,
            authority=decision.authority,
            time_in_force=self.policy.time_in_force,
            limit_price=limit_price,
            stop_price=stop_price,
            take_profit_price=take_profit,
            stop_loss_price=stop_loss,
            client_order_id=f"obsidia-{decision.decision_id}",
            reduce_only=proposal.action in (ActionKind.REDUCE, ActionKind.CLOSE),
            rationale=decision.reason,
        )

    def _limit_price(
        self, order_type: OrderType, last_price: float, action: ActionKind
    ) -> Optional[float]:
        """
        Prix limite derive du dernier prix, decale du slippage tolere dans le
        sens defavorable — on accepte de payer un peu plus a l'achat, de
        recevoir un peu moins a la vente.
        """
        if order_type not in (OrderType.LIMIT, OrderType.STOP_LIMIT):
            return None
        offset = last_price * (self.policy.limit_slippage_bps / 10_000.0)
        side = action.side
        if side is None:
            return round(last_price, 6)
        return round(last_price + offset if side.value == "BUY" else last_price - offset, 6)
