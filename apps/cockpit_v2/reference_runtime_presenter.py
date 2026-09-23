"""
apps/cockpit_v2/reference_runtime_presenter.py — Cockpit V2 Phase A.

Couche de projection LECTURE SEULE. Ne recalcule JAMAIS un verdict, une
permission ou un résultat d'exécution — lit uniquement CycleOutcome (déjà
produit par CycleEngine), ReceiptStore et ReplayEngine.

UI != Authority / UI != Governance / UI != Binder / UI != Execution Engine :
aucune affectation Authority.ACT/HOLD/BLOCK ici, seulement de la lecture
(voir tests/unit/test_cockpit_v2_boundaries.py).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from execution.binder.engine import CycleOutcome
from proof.receipts.receipt_store import ReceiptStore
from proof.receipts.receipt_verify import ReceiptChainVerifier
from proof.receipts.replay import ReplayEngine


def build_human_view(outcome: CycleOutcome, store: ReceiptStore) -> Dict[str, Any]:
    """
    Vue humaine hiérarchisée (Phase A3) : A→G, chacune avec les données
    brutes disponibles sous "technical" pour ne jamais réduire l'auditabilité.
    """
    decision = outcome.decision
    proposal = outcome.proposal or (decision.proposal if decision else None)

    unknowns, contradictions, risk_flags = [], [], []
    for ao in outcome.agent_outputs:
        unknowns.extend(ao.unknowns)
        contradictions.extend(ao.contradictions)
        risk_flags.extend(ao.risk_flags)

    important_signals = sorted(
        (
            {"agent": ao.name, "category": ao.category, "signal": ao.signal, "confidence": ao.confidence}
            for ao in outcome.agent_outputs
        ),
        key=lambda s: s["confidence"],
        reverse=True,
    )[:5]

    return {
        "cycle_id": outcome.cycle_id,
        "A_situation": {
            "symbol": outcome.state.symbols[0] if outcome.state and outcome.state.symbols else None,
            "market_mode": outcome.state.mode.value if outcome.state else None,
            "data_source": "Alpaca paper",
            "market_freshness": "voir technical.domain_state.state pour provenance/quality par symbole",
            "portfolio_summary": (outcome.state.portfolio.as_dict() if outcome.state and outcome.state.portfolio else None),
        },
        "B_cognition": {
            "agent_count": len(outcome.agent_outputs),
            "important_signals": important_signals,
            "unknowns": unknowns,
            "contradictions": contradictions,
            "risk_flags": risk_flags,
        },
        "C_proposal": {
            "action": proposal.action.value if proposal else "AUCUNE (pas de StrategyPort réelle branchée — voir reference_runtime_view.py)",
            "confidence": proposal.consensus.confidence if proposal and proposal.consensus else None,
            "quantity": proposal.sizing.quantity if proposal and proposal.sizing else None,
            "strategy_id": proposal.selected_strategy.strategy_id if proposal and proposal.selected_strategy else None,
            "note": "StrategyPort/SizingPort réelles absentes de ce repo : strategy_id reste vide tant qu'aucune n'est branchée (quantity=0.0 attendu).",
        },
        "D_governance": {
            "x108_decision": decision.authority.value if decision and decision.authority else None,
            "source": "REAL KX108 (RealKX108Client, F12)",
            "reason": decision.reason if decision else None,
        },
        "E_permission": {
            "binder_permission": "ALLOW" if outcome.plan is not None else "REFUSED",
            "banner": "DECISION ≠ PERMISSION",
        },
        "F_execution": _section_execution(outcome),
        "G_proof": _section_proof(outcome, store),
        "technical": _section_technical(outcome, store),
    }


def _section_execution(outcome: CycleOutcome) -> Dict[str, Any]:
    if outcome.execution is None:
        return {"attempted": False, "submitted": False, "status": None, "quantity": None}
    ex = outcome.execution
    return {
        "attempted": True,
        "submitted": ex.submitted,
        "status": ex.status.value if ex.status else None,
        "partial": ex.is_partial,
        "rejected_reason": ex.rejected_reason,
        "quantity": ex.filled_quantity,
        "environment": "PAPER",
    }


def _section_proof(outcome: CycleOutcome, store: ReceiptStore) -> Dict[str, Any]:
    stored = store.find_by_cycle_id(outcome.cycle_id)
    integrity = ReceiptChainVerifier().verify_store(store)
    replay = ReplayEngine(store)
    audit = replay.replay_audit(outcome.cycle_id) if stored is not None else None
    return {
        "proof_policy": "REQUIRED",
        "proof_outcome": outcome.proof_outcome.value if outcome.proof_outcome else None,
        "receipt_persisted": stored is not None,
        "chain_status": integrity.status.value,
        "replay_available": bool(audit and audit.found),
    }


def _section_technical(outcome: CycleOutcome, store: ReceiptStore) -> Dict[str, Any]:
    """Payloads bruts complets, préservés pour l'auditabilité — jamais retirés."""
    stored = store.find_by_cycle_id(outcome.cycle_id)
    return {
        "domain_state": {"state": outcome.state.as_dict() if outcome.state else None},
        "agents": {"count": len(outcome.agent_outputs), "outputs": [ao.as_dict() for ao in outcome.agent_outputs]},
        "decision_raw": outcome.decision.as_dict() if outcome.decision else None,
        "proposal_raw": outcome.proposal.as_dict() if outcome.proposal else None,
        "plan_raw": outcome.plan.as_dict() if outcome.plan else None,
        "execution_raw": outcome.execution.as_dict() if outcome.execution else None,
        "receipt_raw": stored.raw if stored is not None else None,
    }


def build_error_view(error_kind: str, error_message: str) -> Dict[str, Any]:
    """Vue affichée quand le cycle n'a pas pu être lancé/complété (fail-closed, jamais un faux succès)."""
    return {
        "ok": False,
        "error_kind": error_kind,
        "error_message": error_message,
        "banner": "AUCUNE EXÉCUTION — statut fail-closed",
    }
