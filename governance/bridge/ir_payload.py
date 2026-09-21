"""
Governance Bridge — construction de l'IR payload vers KX108 (chantier F5).

Le schema `domain/data:{T_mean,H_score,A_score,S}/meta` reproduit
EXACTEMENT celui du gate reel du core actuel
(obsidia-x108-proofs_REMOTE_A5F21C6B/domains/trading/trading_x108_gate.py
::TradingX108Gate.translate_to_ir), lu en lecture seule pour ce portage.
Reutiliser ce format connu plutot que d'en inventer un nouveau est le choix
le plus honnete : c'est le seul contrat KX108 dont l'existence est averee.

Un bloc `evidence` est ajoute en plus du schema d'origine. Il n'est PAS
consomme pour decider (le Kernel reel peut l'ignorer completement) : il
sert a faire voyager provenance/unknowns/contradictions/risk_flags jusqu'au
Decision/receipt, conformement a la regle de non-perte semantique (F3.5).
"""
from __future__ import annotations

from typing import Any, Dict

from domain.proposal import ActionProposal
from domain.state import TradingDomainState
from governance.bridge.local_signal import LocalStructuralSignal

GATE_VERSION = "v1"
DOMAIN = "trading"

ACTION_TO_FLOW_TYPE: Dict[str, str] = {
    "BUY": "BUY",
    "SELL": "SELL",
    "ADD": "BUY",
    "REDUCE": "SELL",
    "CLOSE": "SELL",
    "KEEP": "POSITION_CHECK",
    "MODIFY_ORDER": "MARKET_ORDER",
    "CANCEL_ORDER": "CANCEL",
    "WAIT": "POSITION_CHECK",
    "NO_ACTION": "POSITION_CHECK",
}


def build_trading_ir_payload(
    proposal: ActionProposal,
    state: TradingDomainState,
    local_signal: LocalStructuralSignal,
) -> Dict[str, Any]:
    """
    Traduit une ActionProposal + son etat de domaine en IR payload KX108.

    IMPORTANT : `local_signal.S` alimente le champ `S` de l'IR comme
    EVIDENCE locale, pas comme verdict — le Kernel reel reste libre de le
    reevaluer, de l'ignorer, ou de calculer sa propre valeur. Rien dans ce
    module ni dans governance_bridge.py ne lit `local_signal.S` pour decider
    de l'autorite : seul le champ "verdict" de la reponse KX108 compte.
    """
    flow_type = ACTION_TO_FLOW_TYPE.get(proposal.action.value, "GENERAL_FLOW")

    agent_outputs = proposal.agent_outputs
    unknowns = tuple(u for o in agent_outputs for u in o.unknowns)
    contradictions = tuple(c for o in agent_outputs for c in o.contradictions)
    risk_flags = tuple(r for o in agent_outputs for r in o.risk_flags)
    evidence_refs = tuple(e for o in agent_outputs for e in o.evidence_refs)

    return {
        "domain": DOMAIN,
        "data": {
            "T_mean": local_signal.T,
            "H_score": local_signal.H,
            "A_score": local_signal.A_norm,
            "S": local_signal.S,
        },
        "meta": {
            "flow_type": flow_type,
            "risk_class": proposal.action.value,
            "gate_version": GATE_VERSION,
            "symbol": proposal.symbol,
            "mode": state.mode.value,
            "state_fingerprint": state.fingerprint(),
        },
        "evidence": {
            "unknowns": list(unknowns),
            "contradictions": list(contradictions),
            "risk_flags": list(risk_flags),
            "evidence_refs": list(evidence_refs),
            "n_agents": local_signal.n_agents,
            "portfolio_context": dict(proposal.portfolio_context),
            "note": (
                "bloc additif non consomme par la decision KX108 ; "
                "transporte pour audit/receipt uniquement (F3.5)"
            ),
        },
    }
