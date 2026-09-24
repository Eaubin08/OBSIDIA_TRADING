"""
fix/broker-ambiguity-truthfulness — un echec apres envoi n'est jamais une
preuve d'absence d'ordre, et une annulation demandee n'est jamais une
annulation confirmee.

Origine : audit adversarial de l'architecture transverse V0.5 (projet du
frere), constats CLA-02-B (retry apres timeout -> double exposition) et
CANCEL_PENDING non terminal (§15.4), appliques au runtime Obsidia.
"""
from __future__ import annotations

import pytest
import requests

from domain.order_ledger import OrderLedgerEvent, OrderLedgerEventType
from domain.orders import ExecutionPlan, ExecutionResult
from domain.portfolio import Order
from domain.proposal import ActionProposal, Consensus, SizingDecision
from domain.receipt import Decision
from domain.types import ActionKind, Authority, Mode, OrderStatus, OrderType, Side
from domain.ports.broker import BrokerUnavailable
from execution.binder.ambiguity_reconciler import reconcile_ambiguous_submissions
from execution.binder.order_ledger_jsonl import JsonlOrderLedger
from market.adapters.alpaca.alpaca_broker import AlpacaBroker
from tests.integration.test_paper_execution_pipeline import FakeBroker, _make_engine
from tests.unit.test_alpaca_providers import FakeResponse, FakeTransport, _client

SYMBOL = "AAPL"
T0 = 1_000_000.0


def _plan(decision_id: str = "d-amb-1", symbol: str = SYMBOL) -> ExecutionPlan:
    return ExecutionPlan(
        decision_id=decision_id,
        symbol=symbol,
        action=ActionKind.BUY,
        side=Side.BUY,
        quantity=1.0,
        order_type=OrderType.MARKET,
        authority=Authority.ACT,
        client_order_id=f"obsidia-{decision_id}",
    )


def _decision(decision_id: str) -> Decision:
    proposal = ActionProposal(
        symbol=SYMBOL,
        action=ActionKind.BUY,
        consensus=Consensus(side="BUY", confidence=0.9),
        sizing=SizingDecision(quantity=1.0, requested_quantity=1.0),
    )
    return Decision(decision_id=decision_id, authority=Authority.ACT, reason="test", proposal=proposal)


def _order(client_order_id: str, status: OrderStatus) -> Order:
    return Order(
        broker_order_id="ord-real-1",
        symbol=SYMBOL,
        side=Side.BUY,
        quantity=1.0,
        order_type=OrderType.MARKET,
        status=status,
        client_order_id=client_order_id,
    )


class _Clock:
    def __init__(self, now: float) -> None:
        self.current = now

    def now(self) -> float:
        return self.current


class _LookupBroker:
    """Broker minimal pour le reconciliateur : seul le lookup compte."""

    def __init__(self, order=None, *, unavailable: bool = False) -> None:
        self.order = order
        self.unavailable = unavailable
        self.lookups = []

    def order_by_client_order_id(self, client_order_id):
        self.lookups.append(client_order_id)
        if self.unavailable:
            raise BrokerUnavailable("reseau coupe")
        return self.order


def _record_ambiguous(ledger: JsonlOrderLedger, plan: ExecutionPlan, at: float = T0) -> None:
    ledger.append(
        OrderLedgerEvent.from_plan(
            event_type=OrderLedgerEventType.SUBMISSION_INTENT_RECORDED,
            cycle_id="c-1", plan=plan, timestamp=at, mode=Mode.PAPER,
        )
    )
    ledger.append(
        OrderLedgerEvent.from_result(
            cycle_id="c-1",
            result=ExecutionResult.ambiguous(plan, "timeout"),
            timestamp=at + 1,
            mode=Mode.PAPER,
        )
    )


# ── Adapter Alpaca : timeout / 5xx != refus ────────────────────────────────


def test_alpaca_submit_timeout_is_ambiguous_never_rejected():
    transport = FakeTransport(
        {
            ("POST", "/v2/orders"): lambda call: (_ for _ in ()).throw(requests.Timeout()),
            ("GET", "/v2/orders:by_client_order_id"): FakeResponse(404, {"message": "not found"}),
        }
    )
    result = AlpacaBroker(_client(transport)).submit(_plan())

    assert result.is_ambiguous is True
    assert result.submitted is True
    assert result.status is OrderStatus.UNKNOWN
    assert result.status is not OrderStatus.REJECTED
    assert "timeout" in result.rejected_reason


def test_alpaca_submit_5xx_is_ambiguous():
    transport = FakeTransport(
        {
            ("POST", "/v2/orders"): FakeResponse(503, {"message": "service unavailable"}),
            ("GET", "/v2/orders:by_client_order_id"): FakeResponse(404, {"message": "not found"}),
        }
    )
    result = AlpacaBroker(_client(transport)).submit(_plan())

    assert result.is_ambiguous is True


def test_alpaca_submit_timeout_resolved_by_client_order_id_lookup():
    transport = FakeTransport(
        {
            ("POST", "/v2/orders"): lambda call: (_ for _ in ()).throw(requests.Timeout()),
            ("GET", "/v2/orders:by_client_order_id"): FakeResponse(
                payload={
                    "id": "ord-found",
                    "symbol": SYMBOL,
                    "status": "new",
                    "client_order_id": "obsidia-d-amb-1",
                    "filled_qty": "0",
                }
            ),
        }
    )
    result = AlpacaBroker(_client(transport)).submit(_plan())

    assert result.is_ambiguous is False
    assert result.status is OrderStatus.ACCEPTED
    assert result.broker_order_id == "ord-found"
    lookup = [c for c in transport.calls if c["method"] == "GET"][-1]
    assert lookup["params"] == {"client_order_id": "obsidia-d-amb-1"}


def test_alpaca_definitive_4xx_stays_an_explicit_rejection():
    transport = FakeTransport(
        {("POST", "/v2/orders"): FakeResponse(403, {"message": "insufficient buying power"})}
    )
    result = AlpacaBroker(_client(transport)).submit(_plan())

    assert result.submitted is False
    assert result.status is OrderStatus.REJECTED
    assert not [c for c in transport.calls if c["method"] == "GET"]  # pas de lookup inutile


# ── Annulation : demandee != confirmee ─────────────────────────────────────


def test_alpaca_pending_cancel_is_not_terminal():
    transport = FakeTransport(
        {
            ("GET", "/v2/orders/ord-1"): FakeResponse(
                payload={
                    "id": "ord-1", "symbol": SYMBOL, "side": "sell", "qty": "5",
                    "type": "stop", "status": "pending_cancel", "stop_price": "95",
                    "time_in_force": "gtc",
                }
            )
        }
    )
    order = AlpacaBroker(_client(transport)).order_status("ord-1")

    assert order.status is OrderStatus.PENDING_CANCEL
    assert order.status.is_terminal is False
    assert order.status.is_open is True


def test_alpaca_cancel_request_returns_pending_cancel_not_canceled():
    transport = FakeTransport({("DELETE", "/v2/orders/ord-1"): FakeResponse(204, payload=None)})
    # 204 sans corps : le client lit json() -> None, accepte comme succes de la demande.
    result = AlpacaBroker(_client(transport)).cancel(_plan(), "ord-1")

    assert result.status is OrderStatus.PENDING_CANCEL
    assert result.status is not OrderStatus.CANCELED


def test_ledger_maps_pending_cancel_to_active_cancel_pending():
    event = OrderLedgerEvent.from_result(
        cycle_id="c-1",
        result=ExecutionResult(
            plan=_plan(), submitted=True, status=OrderStatus.PENDING_CANCEL,
            broker_order_id="ord-1",
        ),
        timestamp=T0,
        mode=Mode.PAPER,
    )
    assert event.event_type is OrderLedgerEventType.CANCEL_PENDING
    assert event.is_terminal is False
    assert event.blocks_submission is True


# ── Lookup Alpaca par client_order_id ──────────────────────────────────────


def test_order_by_client_order_id_uses_direct_endpoint_and_404_means_unknown():
    transport = FakeTransport(
        {("GET", "/v2/orders:by_client_order_id"): FakeResponse(404, {"message": "not found"})}
    )
    assert AlpacaBroker(_client(transport)).order_by_client_order_id("obsidia-x") is None
    assert transport.calls[-1]["params"] == {"client_order_id": "obsidia-x"}


def test_order_by_client_order_id_5xx_is_broker_unavailable_not_absence():
    transport = FakeTransport(
        {("GET", "/v2/orders:by_client_order_id"): FakeResponse(500, {"message": "boom"})}
    )
    with pytest.raises(BrokerUnavailable):
        AlpacaBroker(_client(transport)).order_by_client_order_id("obsidia-x")


# ── Ledger : garde de scope ────────────────────────────────────────────────


def test_not_submitted_result_is_terminal_not_unknown(tmp_path):
    event = OrderLedgerEvent.from_result(
        cycle_id="c-1",
        result=ExecutionResult.not_submitted(_plan(), "autorite insuffisante"),
        timestamp=T0,
        mode=Mode.PAPER,
    )
    assert event.event_type is OrderLedgerEventType.NOT_SUBMITTED
    assert event.is_terminal is True


def test_ambiguous_order_blocks_a_new_decision_on_same_symbol_only(tmp_path):
    ledger = JsonlOrderLedger(tmp_path / "ledger.jsonl")
    _record_ambiguous(ledger, _plan("d-first"))

    blocker = ledger.submission_blocker(_plan("d-second"))
    assert blocker is not None and "reconciliation" in blocker
    assert ledger.submission_blocker(_plan("d-other", symbol="MSFT")) is None


# ── Reconciliation : seule sortie d'une ambiguite ──────────────────────────


def test_reconciler_found_order_unblocks_symbol(tmp_path):
    ledger = JsonlOrderLedger(tmp_path / "ledger.jsonl")
    _record_ambiguous(ledger, _plan("d-first"))
    broker = _LookupBroker(_order("obsidia-d-first", OrderStatus.FILLED))

    notes = reconcile_ambiguous_submissions(ledger, broker, symbol=SYMBOL, now=T0 + 5)

    latest = ledger.latest_by_client_order_id("obsidia-d-first")
    assert latest.event_type is OrderLedgerEventType.FILLED
    assert latest.external_order_id == "ord-real-1"
    assert latest.payload["reconciled_by"] == "client_order_id_lookup"
    assert ledger.submission_blocker(_plan("d-second")) is None
    assert any("reconcilie" in n for n in notes)


def test_reconciler_not_found_before_grace_stays_ambiguous(tmp_path):
    ledger = JsonlOrderLedger(tmp_path / "ledger.jsonl")
    _record_ambiguous(ledger, _plan("d-first"))

    reconcile_ambiguous_submissions(
        ledger, _LookupBroker(None), symbol=SYMBOL, now=T0 + 10, absence_grace_s=60.0
    )

    assert ledger.latest_by_client_order_id("obsidia-d-first").event_type is OrderLedgerEventType.UNKNOWN
    assert ledger.submission_blocker(_plan("d-second")) is not None


def test_reconciler_not_found_after_grace_marks_not_submitted(tmp_path):
    ledger = JsonlOrderLedger(tmp_path / "ledger.jsonl")
    _record_ambiguous(ledger, _plan("d-first"))

    reconcile_ambiguous_submissions(
        ledger, _LookupBroker(None), symbol=SYMBOL, now=T0 + 61, absence_grace_s=60.0
    )

    latest = ledger.latest_by_client_order_id("obsidia-d-first")
    assert latest.event_type is OrderLedgerEventType.NOT_SUBMITTED
    assert ledger.submission_blocker(_plan("d-second")) is None


def test_reconciler_broker_unavailable_keeps_ambiguity(tmp_path):
    ledger = JsonlOrderLedger(tmp_path / "ledger.jsonl")
    _record_ambiguous(ledger, _plan("d-first"))

    notes = reconcile_ambiguous_submissions(
        ledger, _LookupBroker(unavailable=True), symbol=SYMBOL, now=T0 + 3600
    )

    assert ledger.latest_by_client_order_id("obsidia-d-first").event_type is OrderLedgerEventType.UNKNOWN
    assert any("reportee" in n for n in notes)


def test_reconciler_recovers_intent_left_by_crash_before_result(tmp_path):
    # Crash entre "intention persistee" et "resultat persiste" : l'ordre a pu
    # partir. La reprise relit le broker avant toute nouvelle soumission.
    ledger = JsonlOrderLedger(tmp_path / "ledger.jsonl")
    plan = _plan("d-crash")
    ledger.append(
        OrderLedgerEvent.from_plan(
            event_type=OrderLedgerEventType.SUBMISSION_INTENT_RECORDED,
            cycle_id="c-1", plan=plan, timestamp=T0, mode=Mode.PAPER,
        )
    )
    assert ledger.submission_blocker(_plan("d-next")) is not None

    reconcile_ambiguous_submissions(
        ledger, _LookupBroker(_order("obsidia-d-crash", OrderStatus.ACCEPTED)),
        symbol=SYMBOL, now=T0 + 2,
    )

    assert ledger.latest_by_client_order_id("obsidia-d-crash").event_type is OrderLedgerEventType.ACKNOWLEDGED


# ── Bout en bout moteur : plus de double exposition apres timeout ─────────


def test_engine_never_opens_second_order_while_first_is_ambiguous(tmp_path):
    lookups = {"order": None}

    def timeout_then_accept(plan):
        if len(broker.submit_calls) == 1:
            raise BrokerUnavailable("timeout a la soumission")
        return ExecutionResult(plan=plan, submitted=True, status=OrderStatus.ACCEPTED, broker_order_id="ord-2")

    broker = FakeBroker(submit_behavior=timeout_then_accept)
    broker.order_by_client_order_id = lambda cid: lookups["order"]
    ledger = JsonlOrderLedger(tmp_path / "ledger.jsonl")
    engine = _make_engine(verdict="ACT", broker=broker, order_ledger=ledger)
    clock = _Clock(T0)
    engine.clock = clock

    first = engine._execute("c-1", _decision("d-1"), _plan("d-1"), lambda m: None)
    assert first.is_ambiguous is True

    # Nouvelle decision, meme symbole, 10 s plus tard : bloquee, broker non rappele.
    clock.current = T0 + 10
    second = engine._execute("c-2", _decision("d-2"), _plan("d-2"), lambda m: None)
    assert second.submitted is False
    assert "reconciliation" in second.rejected_reason
    assert len(broker.submit_calls) == 1

    # Le premier ordre apparait chez le broker : la reprise le constate,
    # puis une nouvelle decision peut etre soumise.
    lookups["order"] = _order("obsidia-d-1", OrderStatus.FILLED)
    clock.current = T0 + 20
    third = engine._execute("c-3", _decision("d-3"), _plan("d-3"), lambda m: None)
    assert third.status is OrderStatus.ACCEPTED
    assert len(broker.submit_calls) == 2
    assert ledger.latest_by_client_order_id("obsidia-d-1").event_type is OrderLedgerEventType.FILLED
