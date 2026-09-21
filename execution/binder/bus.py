"""
Obsidia Trading — contrat entre le moteur et l'interface.

C'est la piece qui retire a Streamlit la propriete du cycle. L'UI ne peut
faire que trois choses :

    envoyer une commande   -> Command
    lire un etat           -> RuntimeSnapshot
    relire l'historique    -> cycles passes

Elle n'appelle jamais un agent, un broker ou le Guard. Elle ne declenche
jamais un cycle par le simple fait de se redessiner — ce qui etait le defaut
central de ui/app.py, ou chaque mouvement de slider produisait une decision
et ecrivait une preuve.
"""
from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Deque, Dict, List, Optional

from domain.memory import ExperienceRecord, MemoryRecord, MemoryRecordType
from domain.types import Mode
from domain.ports.memory import MemoryPort
from execution.binder.engine import CycleEngine, CycleOutcome
from execution.binder.monitor import ExecutionMonitor, MonitoringReport


class CommandKind(str, Enum):
    """Ce que l'interface a le droit de demander."""

    STEP = "STEP"
    START = "START"
    STOP = "STOP"
    RESET = "RESET"
    MONITOR = "MONITOR"


@dataclass(frozen=True)
class Command:
    kind: CommandKind
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeSnapshot:
    """
    Vue complete de l'etat du runtime, destinee a l'affichage.

    Tout ce dont le cockpit a besoin pour se peindre, et rien de plus : aucune
    reference au moteur, aucun objet mutable partage.
    """

    mode: Mode
    running: bool
    cycle_count: int
    symbols: List[str]
    last_cycle: Optional[Dict[str, Any]] = None
    monitoring: Optional[Dict[str, Any]] = None
    memory: Optional[Dict[str, Any]] = None
    recovery: Optional[Dict[str, Any]] = None
    order_ledger: Optional[Dict[str, Any]] = None
    history: List[Dict[str, Any]] = field(default_factory=list)
    last_error: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "running": self.running,
            "cycle_count": self.cycle_count,
            "symbols": list(self.symbols),
            "last_cycle": self.last_cycle,
            "monitoring": self.monitoring,
            "memory": self.memory,
            "recovery": self.recovery,
            "order_ledger": self.order_ledger,
            "history": list(self.history),
            "last_error": self.last_error,
        }


class RuntimeBus:
    """
    Faade autour du moteur.

    Seul objet que l'interface manipule. Protege par un verrou : deux reruns
    Streamlit simultanes ne peuvent pas declencher deux cycles concurrents.
    """

    def __init__(
        self,
        engine: CycleEngine,
        monitor: Optional[ExecutionMonitor] = None,
        memory: Optional[MemoryPort] = None,
        recovery_report: Optional[Dict[str, Any]] = None,
        history_size: int = 500,
    ) -> None:
        self._engine = engine
        self._monitor = monitor
        self._memory = memory
        self._recovery_report = recovery_report
        self._lock = threading.RLock()
        self._running = False
        self._last_outcome: Optional[CycleOutcome] = None
        self._last_monitoring: Optional[MonitoringReport] = None
        self._last_error: Optional[str] = None
        self._history: Deque[Dict[str, Any]] = deque(maxlen=history_size)

    # ── Commandes ────────────────────────────────────────────────────────

    def send(self, command: Command) -> RuntimeSnapshot:
        """Point d'entree unique de l'interface vers le moteur."""
        with self._lock:
            if command.kind is CommandKind.STEP:
                self._step()
            elif command.kind is CommandKind.START:
                self._running = True
                self._step()
            elif command.kind is CommandKind.STOP:
                self._running = False
            elif command.kind is CommandKind.RESET:
                self._reset()
            elif command.kind is CommandKind.MONITOR:
                self._poll_monitor()
            return self.snapshot()

    def step(self) -> RuntimeSnapshot:
        return self.send(Command(CommandKind.STEP))

    def tick(self) -> RuntimeSnapshot:
        """
        Avance d'un cycle uniquement si le runtime est demarre.

        C'est ce que l'UI appelle dans sa boucle de rafraichissement : se
        redessiner ne suffit plus a produire une decision.
        """
        with self._lock:
            if self._running:
                self._step()
            return self.snapshot()

    # ── Lecture ──────────────────────────────────────────────────────────

    def snapshot(self) -> RuntimeSnapshot:
        return RuntimeSnapshot(
            mode=self._engine.mode,
            running=self._running,
            cycle_count=self._engine.cycle_count,
            symbols=list(self._engine.symbols),
            last_cycle=self._last_outcome.as_dict() if self._last_outcome else None,
            monitoring=self._last_monitoring.as_dict() if self._last_monitoring else None,
            memory=self._memory_status(),
            recovery=self._recovery_report,
            order_ledger=self._order_ledger_status(),
            history=list(self._history),
            last_error=self._last_error,
        )

    @property
    def last_outcome(self) -> Optional[CycleOutcome]:
        """Dernier resultat complet, pour les vues detaillees du cockpit."""
        return self._last_outcome

    @property
    def running(self) -> bool:
        return self._running

    # ── Interne ──────────────────────────────────────────────────────────

    def _step(self) -> None:
        outcome = self._engine.run_cycle()
        self._last_outcome = outcome
        self._last_error = outcome.error

        if self._monitor is not None:
            self._monitor.track(outcome.execution)
            self._poll_monitor(outcome)

        self._write_memory(outcome, self._last_monitoring)
        self._history.append(self._summarize(outcome, self._last_monitoring))

    def _poll_monitor(self, outcome: Optional[CycleOutcome] = None) -> None:
        if self._monitor is None:
            return
        portfolio = outcome.state.portfolio if outcome else None
        self._last_monitoring = self._monitor.poll(
            portfolio, state=outcome.state if outcome else None
        )

    def _reset(self) -> None:
        self._running = False
        self._last_outcome = None
        self._last_monitoring = None
        self._last_error = None
        self._history.clear()

    def _write_memory(
        self,
        outcome: CycleOutcome,
        monitoring: Optional[MonitoringReport],
    ) -> None:
        if self._memory is None or outcome.decision is None:
            return
        timestamp = self._engine.clock.now()
        receipt_hash = outcome.receipt.decision_hash() if outcome.receipt else None
        decision = outcome.decision
        proposal = outcome.proposal
        symbol = proposal.symbol if proposal else None

        records = [
            MemoryRecord(
                memory_id=f"mem:{outcome.cycle_id}:decision",
                record_type=MemoryRecordType.DECISION,
                cycle_id=outcome.cycle_id,
                decision_id=decision.decision_id,
                symbol=symbol,
                timestamp=timestamp,
                payload=decision.as_dict(),
                receipt_hash=receipt_hash,
            )
        ]
        if outcome.execution is not None:
            records.append(
                MemoryRecord(
                    memory_id=f"mem:{outcome.cycle_id}:execution",
                    record_type=MemoryRecordType.EXECUTION,
                    cycle_id=outcome.cycle_id,
                    decision_id=decision.decision_id,
                    symbol=symbol,
                    timestamp=timestamp,
                    payload=outcome.execution.as_dict(),
                    receipt_hash=receipt_hash,
                )
            )
        if monitoring is not None:
            records.append(
                MemoryRecord(
                    memory_id=f"mem:{outcome.cycle_id}:monitoring",
                    record_type=MemoryRecordType.REVIEW,
                    cycle_id=outcome.cycle_id,
                    decision_id=decision.decision_id,
                    symbol=symbol,
                    timestamp=timestamp,
                    payload=monitoring.as_dict(),
                    receipt_hash=receipt_hash,
                )
            )

        for record in records:
            self._append_memory(record)

        if proposal is None:
            return
        execution = outcome.execution
        experience = ExperienceRecord.from_cycle(
            cycle_id=outcome.cycle_id,
            decision_id=decision.decision_id,
            proposal_id=proposal.proposal_id,
            symbol=proposal.symbol,
            action=proposal.action.value,
            authority=decision.authority.value,
            timestamp=timestamp,
            receipt_hash=receipt_hash,
            execution_plan_id=outcome.plan.causal_id if outcome.plan else None,
            execution_status=execution.status.value if execution else None,
            broker_order_id=execution.broker_order_id if execution else None,
            consequence=execution.as_dict() if execution else {"executed": False},
            context={"degraded": outcome.state.is_degraded},
        )
        self._append_memory(
            MemoryRecord(
                memory_id=f"mem:{outcome.cycle_id}:experience",
                record_type=MemoryRecordType.CONSEQUENCE,
                cycle_id=outcome.cycle_id,
                decision_id=decision.decision_id,
                symbol=proposal.symbol,
                timestamp=timestamp,
                payload=experience.as_dict(),
                receipt_hash=receipt_hash,
            )
        )

    def _append_memory(self, record: MemoryRecord) -> None:
        try:
            self._memory.append(record)
        except ValueError:
            return
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"memory persistence failed: {exc}"

    def _memory_status(self) -> Optional[Dict[str, Any]]:
        if self._memory is None:
            return None
        ok, error = self._memory.verify_integrity()
        return {
            "enabled": True,
            "integrity_ok": ok,
            "error": error,
            "path": str(getattr(self._memory, "path", "")),
            "recent_count": len(self._memory.recent(20)) if ok else 0,
        }

    def _order_ledger_status(self) -> Optional[Dict[str, Any]]:
        ledger = getattr(self._engine, "order_ledger", None)
        if ledger is None:
            return None
        ok, error = ledger.verify_integrity()
        return {
            "enabled": True,
            "integrity_ok": ok,
            "error": error,
            "path": str(getattr(ledger, "path", "")),
            "active_orders": len(ledger.non_terminal()) if ok else 0,
        }

    @staticmethod
    def _summarize(
        outcome: CycleOutcome,
        monitoring: Optional[MonitoringReport] = None,
    ) -> Dict[str, Any]:
        """Ligne d'historique compacte, suffisante pour tableaux et graphiques."""
        decision = outcome.decision
        proposal = outcome.proposal
        snapshot = (
            outcome.state.snapshot(proposal.symbol)
            if proposal and proposal.symbol
            else None
        )
        portfolio = outcome.state.portfolio

        return {
            "cycle_id": outcome.cycle_id,
            "symbol": proposal.symbol if proposal else None,
            "price": snapshot.last_price if snapshot else None,
            "authority": decision.authority.value if decision else None,
            "action": proposal.action.value if proposal else None,
            "reason": decision.reason if decision else None,
            "confidence": proposal.consensus.confidence if proposal else None,
            "structural_score": decision.structural_score if decision else None,
            "quantity": proposal.sizing.quantity if proposal else None,
            "equity": portfolio.account.equity if portfolio else None,
            "realized_pnl": portfolio.realized_pnl if portfolio else None,
            "touched_the_market": outcome.touched_the_market,
            "decision_hash": outcome.receipt.decision_hash() if outcome.receipt else None,
            "degraded": outcome.state.is_degraded,
            "monitoring_reviews": len(monitoring.positions) if monitoring else 0,
            "monitoring_proposals": (
                len(monitoring.reevaluation_proposals) if monitoring else 0
            ),
        }
