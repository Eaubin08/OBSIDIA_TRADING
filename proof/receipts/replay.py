"""
Obsidia Trading — replay des cycles proves (chantier F7).

Deux niveaux, strictement separes :

    replay_audit          reconstruit la sequence decisionnelle depuis un
                           receipt stocke, sans rejouer quoi que ce soit.
    replay_deterministic  rejoue une simulation deterministe (F4) si le
                           receipt porte les seed/parametres necessaires, et
                           compare au digest original.

REGLE NON NEGOCIABLE : ce module n'importe JAMAIS `market.adapters.alpaca`
ni `execution.binder.paper_execution` — un replay ne peut structurellement
pas declencher d'ordre broker (verifie par
tests/unit/test_receipt_chain.py::test_replay_has_no_broker_or_binder_import).
Il ne decide rien : un replay ne produit ni ne modifie une `Authority`.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

from proof.receipts.receipt_chain import (
    SIMULATION_EXTENSION_KEY,
    SIMULATION_KIND_TRADING_WORLD,
    build_simulation_extension,
)
from proof.receipts.receipt_store import ReceiptStore, StoredCycleReceipt


@dataclass(frozen=True)
class AuditReplayResult:
    """Reconstruction en lecture seule d'un cycle, depuis son receipt stocke."""

    cycle_id: str
    found: bool
    observed: Optional[Dict[str, Any]] = None
    proposed: Optional[Dict[str, Any]] = None
    kx108_verdict: Optional[Dict[str, Any]] = None
    binder_decision: Optional[Dict[str, Any]] = None
    execution: Optional[Dict[str, Any]] = None


class DeterministicReplayVerdict(str, Enum):
    MATCH = "MATCH"
    DIVERGENCE = "DIVERGENCE"
    NOT_REPLAYABLE = "NOT_REPLAYABLE"


@dataclass(frozen=True)
class DeterministicReplayResult:
    verdict: DeterministicReplayVerdict
    reason: str
    original_digest: Optional[str] = None
    replayed_digest: Optional[str] = None


class ReplayEngine:
    """Reconstruction (audit) et rejeu deterministe (simulation) de cycles proves."""

    def __init__(self, store: ReceiptStore) -> None:
        self._store = store

    # ── Replay audit ─────────────────────────────────────────────────────

    def replay_audit(self, cycle_id: str) -> AuditReplayResult:
        stored = self._store.find_by_cycle_id(cycle_id)
        if stored is None:
            return AuditReplayResult(cycle_id=cycle_id, found=False)

        raw = stored.raw
        decision = raw.get("decision", {})
        proposal = decision.get("proposal", {})
        metrics = decision.get("metrics", {})

        observed = {
            "state_fingerprint": raw.get("state_fingerprint"),
            "mode": raw.get("mode"),
            "degraded_reasons": raw.get("degraded_reasons", []),
        }
        proposed = {
            "symbol": proposal.get("symbol"),
            "action": proposal.get("action"),
            "agent_outputs": proposal.get("agent_outputs", []),
            "unknowns": [u for ao in proposal.get("agent_outputs", []) for u in ao.get("unknowns", [])],
            "contradictions": [
                c for ao in proposal.get("agent_outputs", []) for c in ao.get("contradictions", [])
            ],
            "risk_flags": [
                r for ao in proposal.get("agent_outputs", []) for r in ao.get("risk_flags", [])
            ],
        }
        kx108_verdict = {
            "authority": decision.get("authority"),
            "authority_legacy": decision.get("authority_legacy"),
            "reason": decision.get("reason"),
            "kx108_response": metrics.get("kx108_response"),
            "local_signal": metrics.get("local_signal"),
            "fail_closed": metrics.get("fail_closed", False),
        }
        binder_decision = {
            "execution_plan": raw.get("execution_plan"),
            "touched_the_market": raw.get("touched_the_market"),
        }
        execution = raw.get("execution_result")

        return AuditReplayResult(
            cycle_id=cycle_id,
            found=True,
            observed=observed,
            proposed=proposed,
            kx108_verdict=kx108_verdict,
            binder_decision=binder_decision,
            execution=execution,
        )

    # ── Replay deterministe ──────────────────────────────────────────────

    def replay_deterministic(self, cycle_id: str) -> DeterministicReplayResult:
        stored = self._store.find_by_cycle_id(cycle_id)
        if stored is None:
            return DeterministicReplayResult(
                verdict=DeterministicReplayVerdict.NOT_REPLAYABLE,
                reason=f"cycle_id introuvable: {cycle_id}",
            )

        extension = stored.raw.get("extensions", {}).get(SIMULATION_EXTENSION_KEY)
        if not extension:
            return DeterministicReplayResult(
                verdict=DeterministicReplayVerdict.NOT_REPLAYABLE,
                reason="aucune extension f7_simulation sur ce receipt : "
                "rien a rejouer (le cycle n'a pas produit de simulation "
                "deterministe, ou n'a pas ete attache).",
            )

        if extension.get("kind") != SIMULATION_KIND_TRADING_WORLD:
            return DeterministicReplayResult(
                verdict=DeterministicReplayVerdict.NOT_REPLAYABLE,
                reason=f"type de simulation non pris en charge par ce replay: "
                f"{extension.get('kind')!r}",
            )

        # Import local : garantit que ce module ne cree pas de dependance
        # d'import globale entre proof/receipts/ et simulation/ pour un
        # code qui execute dans la majorite des cas un simple audit replay.
        from simulation.trading_world.market_process import (
            TradingParams,
            run_trading_simulation,
        )

        try:
            params = TradingParams(**extension["params"])
        except TypeError as exc:
            return DeterministicReplayResult(
                verdict=DeterministicReplayVerdict.NOT_REPLAYABLE,
                reason=f"parametres de simulation incompatibles avec le moteur actuel: {exc}",
            )

        steps, returns = run_trading_simulation(params)
        replayed = build_simulation_extension(
            kind=SIMULATION_KIND_TRADING_WORLD,
            seed=params.seed,
            params=extension["params"],
            engine_version=extension.get("engine_version", "unknown"),
            steps=steps,
            returns=returns,
        )

        original_digest = extension["output_digest"]
        replayed_digest = replayed["output_digest"]

        if original_digest == replayed_digest:
            return DeterministicReplayResult(
                verdict=DeterministicReplayVerdict.MATCH,
                reason="rejeu identique au receipt original (meme seed, meme trajectoire)",
                original_digest=original_digest,
                replayed_digest=replayed_digest,
            )
        return DeterministicReplayResult(
            verdict=DeterministicReplayVerdict.DIVERGENCE,
            reason="le rejeu produit une trajectoire differente du receipt original",
            original_digest=original_digest,
            replayed_digest=replayed_digest,
        )
