"""
Tests obligatoires du Governance Bridge (F5, section 19 de la demande de
fusion). Chacun verifie un chemin d'autorite reel, pas un test de fumee.

Rappel de l'architecture testee :
    ActionProposal -> KX108GovernanceBridge.evaluate() -> Decision
                                                              |
                                                    CycleEngine._plan/_execute
                                                    (double barriere, deja
                                                    testee en F3, reproduite
                                                    ici via _broker_gate comme
                                                    dans test_governance_boundary.py)
"""
from __future__ import annotations

import pathlib

import pytest

from domain.orders import ExecutionPlan
from domain.proposal import ActionProposal, AgentOutput, Consensus, SizingDecision
from domain.types import ActionKind, Authority, OrderType, Side
from governance.bridge.governance_bridge import KX108GovernanceBridge
from governance.bridge.kx108_client import (
    KX108Unavailable,
    RaisingKX108Client,
    StaticKX108Client,
    UnavailableKX108Client,
)
from governance.bridge.local_signal import compute_local_structural_signal


def _agent_outputs(signal: str, confidence: float, n: int = 5):
    return tuple(
        AgentOutput(
            name=f"agent-{i}",
            category="TRADING",
            signal=signal,
            confidence=confidence,
            rationale="test",
        )
        for i in range(n)
    )


def _proposal(agent_outputs) -> ActionProposal:
    consensus = Consensus(side="BUY", confidence=0.8)
    sizing = SizingDecision(quantity=1.0, requested_quantity=1.0)
    return ActionProposal(
        symbol="AAPL",
        action=ActionKind.BUY,
        consensus=consensus,
        sizing=sizing,
        agent_outputs=agent_outputs,
    )


def _state():
    from domain.state import TradingDomainState
    from domain.types import Mode

    return TradingDomainState(cycle_id="c1", observed_at=0.0, mode=Mode.SIM)


def _plan(authority: Authority) -> ExecutionPlan:
    return ExecutionPlan(
        decision_id="dec-1",
        symbol="AAPL",
        action=ActionKind.BUY,
        side=Side.BUY,
        quantity=1.0,
        order_type=OrderType.MARKET,
        authority=authority,
    )


class RecordingBroker:
    def __init__(self) -> None:
        self.submit_calls = []

    def submit(self, plan: ExecutionPlan):
        self.submit_calls.append(plan)
        return "SUBMITTED"


def _broker_gate(decision, plan: ExecutionPlan, broker: RecordingBroker) -> None:
    """Reproduit la double barriere de execution/binder/engine.py::_execute
    (meme motif que tests/unit/test_governance_boundary.py)."""
    if not decision.authorizes_action or not plan.is_authorized:
        return
    broker.submit(plan)


# ── 1. score local eleve + KX108 BLOCK -> aucune execution ──────────────


def test_high_local_score_but_kx108_block_blocks_execution() -> None:
    # signal fort : tous les agents d'accord, haute confiance -> S local eleve
    outputs = _agent_outputs("BUY", confidence=0.95, n=7)
    local = compute_local_structural_signal(list(outputs))
    assert local.S > 0.5, "precondition du test : le signal local doit etre fort"

    bridge = KX108GovernanceBridge(client=StaticKX108Client({"verdict": "BLOCK"}))
    decision = bridge.evaluate(_proposal(outputs), _state(), decision_id="d1")

    assert decision.authority is Authority.BLOCK
    assert decision.structural_score == pytest.approx(local.S)

    broker = RecordingBroker()
    _broker_gate(decision, _plan(decision.authority), broker)
    assert broker.submit_calls == [], "un score local eleve ne doit jamais outrepasser un BLOCK KX108"


# ── 2. score local eleve + KX108 HOLD -> aucune execution ────────────────


def test_high_local_score_but_kx108_hold_blocks_execution() -> None:
    outputs = _agent_outputs("BUY", confidence=0.95, n=7)
    bridge = KX108GovernanceBridge(client=StaticKX108Client({"verdict": "HOLD"}))
    decision = bridge.evaluate(_proposal(outputs), _state(), decision_id="d2")

    assert decision.authority is Authority.HOLD

    broker = RecordingBroker()
    _broker_gate(decision, _plan(decision.authority), broker)
    assert broker.submit_calls == [], "un score local eleve ne doit jamais outrepasser un HOLD KX108"


# ── 3. score local faible + KX108 ACT -> le Binder reste libre de refuser ─


def test_low_local_score_but_kx108_act_still_gated_by_binder() -> None:
    # signal faible : agents en desaccord -> S local bas
    outputs = tuple(
        AgentOutput(name=f"agent-{i}", category="TRADING", signal=s, confidence=0.3, rationale="test")
        for i, s in enumerate(["BUY", "SELL", "HOLD", "SELL", "BUY"])
    )
    local = compute_local_structural_signal(list(outputs))

    bridge = KX108GovernanceBridge(client=StaticKX108Client({"verdict": "ACT"}))
    decision = bridge.evaluate(_proposal(outputs), _state(), decision_id="d3")

    assert decision.authority is Authority.ACT, "KX108 dit ACT : le bridge doit le respecter meme si le signal local est faible"
    assert decision.structural_score == pytest.approx(local.S)

    # Le Binder (double barriere) reste un controle INDEPENDANT du score local :
    # ici on simule un plan mal cable (authority differente) pour prouver que
    # le passage par le bridge ne court-circuite pas cette barriere.
    broker = RecordingBroker()
    mismatched_plan = _plan(Authority.HOLD)  # plan.is_authorized sera False malgre Decision.ACT
    _broker_gate(decision, mismatched_plan, broker)
    assert broker.submit_calls == [], "le Binder doit rester capable de refuser meme apres un ACT du bridge"

    # Et le chemin nominal (plan correctement autorise) doit, lui, executer :
    broker2 = RecordingBroker()
    correct_plan = _plan(Authority.ACT)
    _broker_gate(decision, correct_plan, broker2)
    assert len(broker2.submit_calls) == 1, "ACT + plan correctement autorise doit permettre l'execution (paper)"


# ── 4. KX108 indisponible -> aucune execution, fail-closed explicite ─────


def test_kx108_unavailable_fails_closed() -> None:
    outputs = _agent_outputs("BUY", confidence=0.9, n=5)
    bridge = KX108GovernanceBridge(client=UnavailableKX108Client())
    decision = bridge.evaluate(_proposal(outputs), _state(), decision_id="d4")

    assert decision.authority is Authority.HOLD, "KX108 indisponible doit fail-closed en HOLD, jamais ACT"
    assert decision.metrics.get("fail_closed") is True
    assert "indisponible" in decision.reason.lower()

    broker = RecordingBroker()
    _broker_gate(decision, _plan(decision.authority), broker)
    assert broker.submit_calls == []


def test_kx108_raises_unexpected_exception_fails_closed() -> None:
    outputs = _agent_outputs("BUY", confidence=0.9, n=5)
    bridge = KX108GovernanceBridge(client=RaisingKX108Client(TimeoutError("simulated timeout")))
    decision = bridge.evaluate(_proposal(outputs), _state(), decision_id="d4b")

    assert decision.authority is Authority.HOLD
    assert decision.metrics.get("fail_closed") is True

    broker = RecordingBroker()
    _broker_gate(decision, _plan(decision.authority), broker)
    assert broker.submit_calls == []


# ── 5. reponse KX108 invalide -> aucune execution, fail-closed ───────────


@pytest.mark.parametrize(
    "bad_response",
    [
        {},  # pas de cle "verdict"
        {"verdict": "MAYBE"},  # verdict inconnu
        {"verdict": 42},  # type incorrect
        {"verdict": None},
        "not-a-dict",  # reponse non-dict
    ],
)
def test_kx108_invalid_response_fails_closed(bad_response) -> None:
    outputs = _agent_outputs("BUY", confidence=0.9, n=5)
    bridge = KX108GovernanceBridge(client=StaticKX108ClientRaw(bad_response))
    decision = bridge.evaluate(_proposal(outputs), _state(), decision_id="d5")

    assert decision.authority is Authority.HOLD, f"reponse invalide {bad_response!r} doit fail-closed en HOLD"
    assert decision.metrics.get("fail_closed") is True

    broker = RecordingBroker()
    _broker_gate(decision, _plan(decision.authority), broker)
    assert broker.submit_calls == []


class StaticKX108ClientRaw:
    """Comme StaticKX108Client, mais accepte une reponse brute non-dict pour
    tester la robustesse du parsing (StaticKX108Client fait `dict(response)`
    ce qui echouerait avant meme d'atteindre le bridge)."""

    def __init__(self, response) -> None:
        self._response = response

    def evaluate_trading(self, ir_payload):
        return self._response


# ── 6. aucun chemin direct Domain/Agent/Simulation -> Binder ─────────────


def _has_forbidden_import(content: str, forbidden_module: str) -> bool:
    """Vrai si une ligne `import X` / `from X import ...` reference reellement
    `forbidden_module` — ignore les mentions en commentaire/docstring."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith(f"import {forbidden_module}") or stripped.startswith(
            f"from {forbidden_module}"
        ):
            return True
        if stripped.startswith(f"import {forbidden_module}.") or stripped.startswith(
            f"from {forbidden_module}."
        ):
            return True
    return False


def test_no_direct_import_from_domain_or_agents_or_simulation_to_binder() -> None:
    """Le seul chemin autorise vers execution.binder est via
    governance.bridge (qui l'implemente comme AuthorityPort, sans
    l'importer lui-meme). domain/, native/agents/ et simulation/ ne
    doivent jamais importer execution.binder directement."""
    forbidden_roots = ["domain", "native/agents", "simulation"]
    for root in forbidden_roots:
        for path in pathlib.Path(root).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            content = path.read_text(encoding="utf-8")
            assert not _has_forbidden_import(content, "execution.binder"), (
                f"{path} importe execution.binder directement — "
                "seul le Governance Bridge doit etre injecte comme AuthorityPort"
            )


# ── 7. aucun chemin direct Governance Bridge -> Broker ───────────────────


def test_no_direct_import_from_governance_bridge_to_broker_or_alpaca() -> None:
    """governance/bridge/ ne doit jamais importer market.adapters.alpaca ni
    aucun module broker directement : le seul chemin Bridge->Broker passe
    par execution/binder (qui recoit Decision.authority, jamais l'inverse)."""
    bridge_dir = pathlib.Path("governance/bridge")
    for path in bridge_dir.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        content = path.read_text(encoding="utf-8")
        assert "market.adapters.alpaca" not in content, f"{path} ne doit pas importer le broker Alpaca"
        assert "execution.binder" not in content, f"{path} ne doit pas importer execution.binder (sens interdit)"
        assert ".submit(" not in content, f"{path} ne doit jamais soumettre d'ordre directement"
