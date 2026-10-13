"""
Reconciliation des soumissions ambigues (fix/broker-ambiguity-truthfulness).

Un timeout ou une coupure pendant la soumission n'est ni un fill ni une
preuve d'absence d'ordre. Le ledger garde donc l'ordre dans un etat ambigu
(voir AMBIGUOUS_SCOPE_EVENTS) et `JsonlOrderLedger.submission_blocker` refuse
toute nouvelle soumission sur le symbole. Ce module est le seul chemin de
sortie : il interroge le broker par client_order_id et n'ecrit dans le ledger
que ce qui a ete observe.

Pure persistance + observation : il ne decide rien, ne soumet rien, n'annule
rien. Il ne fabrique jamais un fill.

Hypothese de contrat broker (explicite, parametrable) : un client_order_id est
unique chez le broker et son lookup direct fait autorite. Une absence n'est
donc tenue pour prouvee que si le lookup repond "inconnu" apres un delai de
grace mesure depuis l'enregistrement de l'intention — le temps qu'une requete
encore en vol ait ete traitee. Avant ce delai, l'ordre reste ambigu.
"""
from __future__ import annotations

from typing import List

from domain.order_ledger import (
    AMBIGUOUS_SCOPE_EVENTS,
    OrderLedgerEvent,
    OrderLedgerEventType,
    event_type_from_order_status,
)
from domain.ports.broker import BrokerPort, BrokerUnavailable
from domain.ports.order_ledger import OrderLedgerPort

# Delai minimal entre l'intention enregistree et une conclusion "ordre absent".
# Parametre de contrat broker, pas une constante financiere : surchargeable
# via CycleEngine(ambiguity_absence_grace_s=...).
DEFAULT_ABSENCE_GRACE_S = 60.0


def reconcile_ambiguous_submissions(
    ledger: OrderLedgerPort,
    broker: BrokerPort,
    *,
    symbol: str,
    now: float,
    absence_grace_s: float = DEFAULT_ABSENCE_GRACE_S,
) -> List[str]:
    """
    Tente de resoudre les ordres ambigus du symbole. Retourne des notes
    lisibles ; n'echoue jamais bruyamment (un broker injoignable laisse
    simplement l'ambiguite en place, donc le symbole bloque).
    """
    notes: List[str] = []
    for pending in ledger.non_terminal():
        if pending.symbol != symbol or pending.event_type not in AMBIGUOUS_SCOPE_EVENTS:
            continue
        label = pending.client_order_id or pending.ledger_id
        if not pending.client_order_id:
            notes.append(f"reconciliation impossible pour {label} : aucun client_order_id")
            continue

        try:
            order = broker.order_by_client_order_id(pending.client_order_id)
        except BrokerUnavailable as exc:
            notes.append(f"reconciliation de {label} reportee : broker indisponible ({exc})")
            continue

        if order is not None:
            observed = event_type_from_order_status(order.status, submitted=True)
            if observed is pending.event_type:
                notes.append(f"{label} toujours {observed.value} chez le broker")
                continue
            ledger.append(
                OrderLedgerEvent.from_reconciliation(
                    prior=pending,
                    event_type=observed,
                    timestamp=now,
                    external_order_id=order.broker_order_id or None,
                    status=order.status.value,
                    payload={
                        "reconciled_by": "client_order_id_lookup",
                        "previous_event": pending.event_type.value,
                        "broker_status": order.status.value,
                        "filled_quantity": order.filled_quantity,
                    },
                )
            )
            notes.append(
                f"{label} reconcilie : {pending.event_type.value} -> {observed.value} "
                f"(observe chez le broker)"
            )
            continue

        intent_at = _first_timestamp(ledger, pending)
        if now - intent_at < absence_grace_s:
            notes.append(
                f"{label} introuvable chez le broker mais delai de grace non ecoule "
                f"({now - intent_at:.1f}s < {absence_grace_s:.1f}s) : reste ambigu"
            )
            continue

        ledger.append(
            OrderLedgerEvent.from_reconciliation(
                prior=pending,
                event_type=OrderLedgerEventType.NOT_SUBMITTED,
                timestamp=now,
                external_order_id=None,
                status=OrderLedgerEventType.NOT_SUBMITTED.value,
                payload={
                    "reconciled_by": "client_order_id_lookup",
                    "previous_event": pending.event_type.value,
                    "absence_grace_s": absence_grace_s,
                    "reason": "client_order_id inconnu du broker apres delai de grace",
                },
            )
        )
        notes.append(f"{label} absent chez le broker apres delai de grace : NOT_SUBMITTED")
    return notes


def _first_timestamp(ledger: OrderLedgerPort, pending: OrderLedgerEvent) -> float:
    history = ledger.events(pending.ledger_id)
    return min((e.timestamp for e in history), default=pending.timestamp)
