"""
apps/cockpit/presenter.py — F9.

Assemble les 11 sections d'affichage a partir de CE QUE LE RUNTIME A DEJA
PRODUIT (``CycleOutcome``, ``ReceiptStore``, ``ReplayEngine``). Ce module ne
recalcule JAMAIS un verdict, une permission, ou un resultat d'execution — il
lit uniquement des objets deja construits par ``CycleEngine`` (F3/F6),
``KX108GovernanceBridge`` (F5) et ``ReplayEngine`` (F7).

UI != Authority / UI != Governance / UI != Binder / UI != Execution Engine :
aucune fonction ici ne contient d'instruction ``Authority.ACT`` /
``Authority.HOLD`` / ``Authority.BLOCK`` en tant qu'AFFECTATION — seulement en
LECTURE d'un objet deja decide ailleurs (voir tests/unit/test_cockpit.py,
test structurel dedie).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from execution.binder.engine import CycleOutcome
from proof.receipts.receipt_chain import SIMULATION_EXTENSION_KEY
from proof.receipts.receipt_store import ReceiptStore
from proof.receipts.receipt_verify import ReceiptChainVerifier
from proof.receipts.replay import ReplayEngine

KX108_FIXTURE_BANNER = "TEST FIXTURE — NOT REAL KX108"


def build_cockpit_view(outcome: CycleOutcome, store: ReceiptStore) -> Dict[str, Any]:
    """Construit la vue complete d'un cycle deja execute. Lecture seule."""
    decision = outcome.decision
    proposal = outcome.proposal or (decision.proposal if decision else None)

    view: Dict[str, Any] = {
        "cycle_id": outcome.cycle_id,
        "input": _section_input(outcome),
        "domain_state": _section_domain_state(outcome),
        "agents": _section_agents(outcome),
        "simulation": _section_simulation(outcome),
        "intent": _section_intent(proposal),
        "governance": _section_governance(decision),
        "kx108": _section_kx108(decision),
        "binder": _section_binder(outcome),
        "execution": _section_execution(outcome),
        "receipt": _section_receipt(outcome, store),
        "replay": _section_replay(outcome, store),
    }
    return view


# ── Sections ─────────────────────────────────────────────────────────────


def _section_input(outcome: CycleOutcome) -> Dict[str, Any]:
    provenances = [
        ao.source_provenance.as_dict()
        for ao in outcome.agent_outputs
        if ao.source_provenance is not None
    ]
    distinct_systems = sorted({p["source_system"] for p in provenances}) if provenances else []
    return {
        "source_systems_observed": distinct_systems,
        "provenances": provenances,
        "observed_at": outcome.state.observed_at if outcome.state else None,
        "mode": outcome.state.mode.value if outcome.state else None,
        # F15 : detail par source, pour rendre visible "ce que la stack
        # propose" (Native ou External) avant toute decision de gouvernance.
        # Lecture seule des champs deja produits par le runtime (F3.5/F15) —
        # aucune valeur n'est devinee si un champ (ex: calibration externe)
        # est absent du signal d'origine.
        "external_stack_readiness": _section_external_stack_detail(outcome),
    }


def _section_external_stack_detail(outcome: CycleOutcome) -> Dict[str, Any]:
    """
    F15 — detail des signaux SOURCE=EXTERNAL de ce cycle, s'il y en a.

    N'affecte jamais Authority/Decision : lit uniquement `AgentOutput` deja
    produits (source_provenance + inputs_digest, remplis par
    `external/normalization/normalizer.py`). Rien n'est recalcule.
    """
    entries = []
    for ao in outcome.agent_outputs:
        prov = ao.source_provenance
        if prov is None or prov.source_system.value != "external":
            continue
        entries.append(
            {
                "stack_id": prov.source_id,
                "adapter_id": prov.adapter_id,
                "organization_id": prov.organization_id,
                "strategy_id": ao.inputs_digest.get("strategy_id"),
                "symbol": ao.inputs_digest.get("symbol"),
                "proposal": ao.signal,
                "confidence": ao.confidence,
                "unknowns": list(ao.unknowns),
                "contradictions": list(ao.contradictions),
                "risk_flags": list(ao.risk_flags),
                "evidence_refs": list(ao.evidence_refs),
                "external_calibration_id": ao.inputs_digest.get("external_calibration_id"),
            }
        )
    return {"present": bool(entries), "signals": entries}


def _section_domain_state(outcome: CycleOutcome) -> Dict[str, Any]:
    state_dict = outcome.state.as_dict() if outcome.state else {}
    unknowns, contradictions, risk_flags, evidence_refs = [], [], [], []
    for ao in outcome.agent_outputs:
        unknowns.extend(ao.unknowns)
        contradictions.extend(ao.contradictions)
        risk_flags.extend(ao.risk_flags)
        evidence_refs.extend(ao.evidence_refs)
    return {
        "state": state_dict,
        "unknowns": unknowns,
        "contradictions": contradictions,
        "risk_flags": risk_flags,
        "evidence_refs": evidence_refs,
    }


def _section_agents(outcome: CycleOutcome) -> Dict[str, Any]:
    # Sorties REELLEMENT produites par les agents executes — jamais une valeur
    # inventee si un agent n'a rien produit pour ce cycle.
    return {
        "count": len(outcome.agent_outputs),
        "outputs": [ao.as_dict() for ao in outcome.agent_outputs],
    }


def _section_simulation(outcome: CycleOutcome) -> Dict[str, Any]:
    extension = None
    if outcome.receipt is not None:
        extension = outcome.receipt.extensions.get(SIMULATION_EXTENSION_KEY)
    return {
        "attached": extension is not None,
        "evidence": extension,
        "banner": "SIMULATION ≠ AUTHORITY",
    }


def _section_intent(proposal) -> Dict[str, Any]:
    return {
        "proposal": proposal.as_dict() if proposal else None,
        "banner": "INTENT ≠ ACTION",
    }


def _section_governance(decision) -> Dict[str, Any]:
    if decision is None:
        return {"local_signal": None, "structural_score": None}
    metrics = decision.metrics or {}
    return {
        "local_signal": metrics.get("local_signal"),
        "structural_score": decision.structural_score,
        "note": "le score local est une Evidence transportee, jamais le verdict — voir docs/B15_STRUCTURAL_SCORE_BOUNDARY.md",
    }


def _section_kx108(decision) -> Dict[str, Any]:
    kx108_response = (decision.metrics or {}).get("kx108_response") if decision else None
    return {
        "authority": decision.authority.value if decision and decision.authority else None,
        "reason": decision.reason if decision else None,
        "response": kx108_response,
        "banner": KX108_FIXTURE_BANNER,  # inconditionnel : ce Cockpit n'a jamais de vrai Kernel branche
    }


def _section_binder(outcome: CycleOutcome) -> Dict[str, Any]:
    kx108_authority = outcome.decision.authority.value if outcome.decision and outcome.decision.authority else None
    permission_granted = outcome.plan is not None
    return {
        "kx108_decision": kx108_authority,
        "binder_permission_granted": permission_granted,
        "plan": outcome.plan.as_dict() if outcome.plan else None,
        "banner": "DECISION ≠ PERMISSION",
    }


def _section_execution(outcome: CycleOutcome) -> Dict[str, Any]:
    if outcome.execution is None:
        return {"attempted": False, "result": None, "environment": "PAPER"}
    return {
        "attempted": True,
        "result": outcome.execution.as_dict(),
        "environment": "PAPER",  # F9 ne construit jamais l'environnement live, voir scenarios.py
    }


def _section_receipt(outcome: CycleOutcome, store: ReceiptStore) -> Dict[str, Any]:
    stored = store.find_by_cycle_id(outcome.cycle_id)
    integrity = ReceiptChainVerifier().verify_store(store)
    if stored is None:
        return {"persisted": False, "chain_integrity": integrity.status.value}
    return {
        "persisted": True,
        "cycle_id": stored.cycle_id,
        "receipt_schema_version": stored.receipt_schema_version,
        "current_hash": stored.stored_hash,
        "previous_hash": stored.previous_receipt_hash,
        "authority": stored.authority,
        "chain_integrity": integrity.status.value,
        "raw": stored.raw,
    }


def _section_replay(outcome: CycleOutcome, store: ReceiptStore) -> Dict[str, Any]:
    # Replay audit immediat, zero effet de bord (ReplayEngine, F7, reutilise
    # tel quel) — utile pour verifier a chaque cycle que le receipt persiste
    # se rejoue correctement, independamment du scenario 8 (replay d'un cycle
    # choisi librement par l'utilisateur).
    replay = ReplayEngine(store)
    audit = replay.replay_audit(outcome.cycle_id)
    return {
        "audit_found": audit.found,
        "audit_kx108_verdict": audit.kx108_verdict,
        "audit_execution": audit.execution,
    }


def build_replay_view(store: ReceiptStore, cycle_id: str) -> Dict[str, Any]:
    """Vue du scenario 8 : replay explicite d'un cycle deja persiste, choisi par l'utilisateur."""
    from apps.cockpit.scenarios import replay_previous_cycle

    audit, deterministic = replay_previous_cycle(store, cycle_id)
    return {
        "cycle_id": cycle_id,
        "audit": {
            "found": audit.found,
            "observed": audit.observed,
            "proposed": audit.proposed,
            "kx108_verdict": audit.kx108_verdict,
            "binder_decision": audit.binder_decision,
            "execution": audit.execution,
        },
        "deterministic": {
            "verdict": deterministic.verdict.value,
            "reason": deterministic.reason,
            "original_digest": deterministic.original_digest,
            "replayed_digest": deterministic.replayed_digest,
        },
        "banner": "REPLAY ≠ EXECUTION — aucun appel broker n'a lieu pendant un replay",
    }
