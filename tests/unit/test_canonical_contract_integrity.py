"""
F3.5 - Canonical Contract Closure : preuve de non-perte semantique.

Ces tests construisent un cycle minimal (agent -> AgentOutput -> ActionProposal
-> Decision -> CycleReceipt) et verifient qu'un `unknown`, une
`contradiction` et un `risk_flag` produits par un agent restent
retrouvables jusque dans le contenu hashable du receipt final.

Si quelqu'un reintroduit une compression/perte silencieuse (par exemple en
remettant unknowns/contradictions/risk_flags dans un `inputs_digest` opaque
qui finit par etre resume ou tronque), ces tests doivent echouer.
"""
from __future__ import annotations

import time

from domain.contracts.canonical import (
    CanonicalCycleView,
    to_canonical_agent_signal,
)
from domain.proposal import ActionProposal, Consensus, SizingDecision
from domain.receipt import CycleReceipt, Decision
from domain.state import TradingDomainState
from domain.types import ActionKind, Authority, Mode


def _minimal_state() -> TradingDomainState:
    return TradingDomainState(
        cycle_id="cycle-test-001",
        observed_at=time.time(),
        mode=Mode.SIM,
    )


def _cycle_view_with_signal(signal) -> CanonicalCycleView:
    state = _minimal_state()

    consensus = Consensus(side="HOLD", confidence=0.5)
    sizing = SizingDecision(quantity=0.0, requested_quantity=0.0)
    proposal = ActionProposal(
        symbol="TEST/USD",
        action=ActionKind.KEEP,
        consensus=consensus,
        sizing=sizing,
        agent_outputs=(signal,),
    )
    decision = Decision(
        decision_id="decision-test-001",
        authority=Authority.HOLD,
        reason="test: aucun instrument pret",
        proposal=proposal,
    )
    receipt = CycleReceipt(
        cycle_id=state.cycle_id,
        decision_id=decision.decision_id,
        recorded_at=time.time(),
        mode=state.mode,
        state_fingerprint=state.fingerprint(),
        decision=decision,
    )
    return CanonicalCycleView(
        state=state,
        agent_signals=(signal,),
        proposal=proposal,
        decision=decision,
        receipt=receipt,
    )


def test_unknown_survives_agent_to_receipt():
    signal = to_canonical_agent_signal(
        agent_id="MarketDataAgent",
        category="TRADING",
        signal="HOLD",
        confidence=0.4,
        rationale="donnee de marche incomplete",
        unknowns=("UNKNOWN::spread_bps_missing_for_TEST/USD",),
    )
    view = _cycle_view_with_signal(signal)

    assert "UNKNOWN::spread_bps_missing_for_TEST/USD" in view.all_unknowns()
    assert "UNKNOWN::spread_bps_missing_for_TEST/USD" in view.decision.as_dict()["proposal"]["agent_outputs"][0]["unknowns"]
    assert view.receipt_preserves_agent_semantics()


def test_contradiction_survives_agent_to_receipt():
    signal = to_canonical_agent_signal(
        agent_id="MomentumAgent",
        category="TRADING",
        signal="BUY",
        confidence=0.6,
        rationale="momentum haussier",
        contradictions=("CONTRADICTION::momentum_up_but_regime_bearish",),
    )
    view = _cycle_view_with_signal(signal)

    assert "CONTRADICTION::momentum_up_but_regime_bearish" in view.all_contradictions()
    assert (
        "CONTRADICTION::momentum_up_but_regime_bearish"
        in view.decision.as_dict()["proposal"]["agent_outputs"][0]["contradictions"]
    )
    assert view.receipt_preserves_agent_semantics()


def test_risk_flag_survives_agent_to_receipt():
    signal = to_canonical_agent_signal(
        agent_id="PortfolioStressAgent",
        category="TRADING",
        signal="HOLD",
        confidence=0.3,
        rationale="exposition proche du seuil de stress",
        risk_flags=("RISK::portfolio_exposure_near_stress_threshold",),
    )
    view = _cycle_view_with_signal(signal)

    assert "RISK::portfolio_exposure_near_stress_threshold" in view.all_risk_flags()
    assert (
        "RISK::portfolio_exposure_near_stress_threshold"
        in view.decision.as_dict()["proposal"]["agent_outputs"][0]["risk_flags"]
    )
    assert view.receipt_preserves_agent_semantics()


def test_regression_guard_would_catch_silent_compression():
    """
    Filet de securite explicite : si un jour quelqu'un range de nouveau les
    unknowns/contradictions/risk_flags UNIQUEMENT dans inputs_digest (sans
    les champs de premiere classe), ce test le detecte car
    `receipt_preserves_agent_semantics` cherche le token dans le contenu
    hashable, mais `all_unknowns()` lit exclusivement les champs de
    premiere classe de CanonicalAgentSignal.
    """
    signal = to_canonical_agent_signal(
        agent_id="EventAgent",
        category="TRADING",
        signal="HOLD",
        confidence=0.5,
        rationale="risque d'evenement macro",
        unknowns=("UNKNOWN::event_calendar_unavailable",),
    )
    # Un agent qui ne passerait PAS par to_canonical_agent_signal et
    # rangerait le meme unknown uniquement dans inputs_digest ne serait pas
    # detecte par all_unknowns() : c'est exactement le risque a ne jamais
    # reintroduire.
    assert signal.unknowns == ("UNKNOWN::event_calendar_unavailable",)
    assert "UNKNOWN::event_calendar_unavailable" not in signal.inputs_digest
