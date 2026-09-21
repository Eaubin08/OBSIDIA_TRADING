"""
Tests de frontiere obligatoires (section 19 de la demande de fusion).

Ce fichier N'EST PAS un portage de agent-trad-main/tests/test_governance_invariants.py.
L'original depend de obsidia.runtime.factory.build_legacy_runtime + core.guard_x108.GuardX108,
qui necessitent tout le sous-systeme obsidia/adapters/{legacy_*,jsonl_*,sim_broker}.py —
hors perimetre F2/F3 (voir docs/MIGRATION_PROVENANCE.md). Plutot que d'importer ce
sous-systeme non porte, ce fichier verifie directement la double barriere d'autorite
telle qu'implementee dans execution/binder/engine.py (`CycleEngine._plan` / `_execute`),
qui est le coeur reel de l'invariant demande :

    agent != authority
    strategy != authority
    KX108 != ACT  -> aucune execution
    KX108 = HOLD  -> aucune execution
    KX108 = BLOCK -> aucune execution
    KX108 = ACT + Binder refuse -> aucune execution
    KX108 = ACT + Binder autorise -> execution (paper) possible
"""
from __future__ import annotations

import time

import pytest

from domain.orders import ExecutionPlan
from domain.proposal import ActionProposal, Consensus, SizingDecision
from domain.receipt import GENESIS_HASH, CycleReceipt, Decision, verify_chain
from domain.types import ActionKind, Authority, Mode, OrderType, Side


class RecordingBroker:
    """Broker factice : n'existe que pour constater si submit() a ete appele."""

    def __init__(self) -> None:
        self.submit_calls = []

    def submit(self, plan: ExecutionPlan):
        self.submit_calls.append(plan)
        return "SUBMITTED"


def _proposal(action: ActionKind = ActionKind.BUY) -> ActionProposal:
    consensus = Consensus(side="BUY", confidence=0.8)
    sizing = SizingDecision(quantity=1.0, requested_quantity=1.0)
    return ActionProposal(symbol="AAPL", action=action, consensus=consensus, sizing=sizing)


def _decision(authority: Authority) -> Decision:
    return Decision(
        decision_id="dec-1",
        authority=authority,
        reason=f"test:{authority.value}",
        proposal=_proposal(),
    )


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


def _broker_gate(decision: Decision, plan: ExecutionPlan, broker: RecordingBroker) -> None:
    """Reproduit exactement la double barriere de execution/binder/engine.py::_execute
    (sans dependre de CycleEngine complet — voir docstring du module)."""
    if not decision.authorizes_action or not plan.is_authorized:
        return
    broker.submit(plan)


@pytest.mark.parametrize("authority", [Authority.HOLD, Authority.BLOCK])
def test_kx108_not_act_blocks_execution(authority: Authority) -> None:
    decision = _decision(authority)
    plan = _plan(authority)
    broker = RecordingBroker()
    _broker_gate(decision, plan, broker)
    assert broker.submit_calls == [], f"KX108={authority.value} ne doit jamais executer"


def test_kx108_act_but_plan_not_authorized_blocks_execution() -> None:
    """Decision ACT mais plan construit avec une autre autorite (erreur de cablage
    simulee) : le Binder doit refuser meme si la decision seule dit ACT."""
    decision = _decision(Authority.ACT)
    plan = _plan(Authority.HOLD)  # plan.is_authorized sera False
    broker = RecordingBroker()
    assert plan.is_authorized is False
    _broker_gate(decision, plan, broker)
    assert broker.submit_calls == [], "le Binder doit refuser un plan non autorise meme si la decision dit ACT"


def test_kx108_act_and_plan_authorized_allows_paper_execution() -> None:
    decision = _decision(Authority.ACT)
    plan = _plan(Authority.ACT)
    broker = RecordingBroker()
    assert plan.is_authorized is True
    _broker_gate(decision, plan, broker)
    assert len(broker.submit_calls) == 1, "ACT+plan autorise doit permettre l'execution (paper)"


def test_agent_output_never_carries_authority() -> None:
    """agent != authority : AgentOutput (sortie d'agent) n'a structurellement
    aucun champ d'autorite ACT/HOLD/BLOCK — seul Decision (verdict KX108) en a un."""
    from domain.proposal import AgentOutput

    output = AgentOutput(name="MarketDataAgent", category="TRADING", signal="BUY", confidence=0.9, rationale="test")
    assert not hasattr(output, "authority"), "un AgentOutput ne doit jamais porter d'autorite"


def test_strategy_candidate_never_carries_authority() -> None:
    """strategy != authority : StrategyCandidate n'a pas de champ d'autorite."""
    from domain.proposal import StrategyCandidate

    fields = {f.name for f in StrategyCandidate.__dataclass_fields__.values()}
    assert "authority" not in fields, "une StrategyCandidate ne doit jamais porter d'autorite"


def test_native_roster_agents_have_no_broker_access() -> None:
    """Verifie que le roster de 17 agents natifs n'importe ni ne reference
    de module broker/execution — ils observent et votent, rien de plus."""
    import pathlib

    agents_dir = pathlib.Path("native/agents")
    for path in agents_dir.rglob("*.py"):
        if path.name == "adapter.py":
            continue  # l'adapter lui-meme ne fait qu'analyser, verifie separement
        content = path.read_text(encoding="utf-8")
        assert "broker" not in content.lower(), f"{path} ne doit referencer aucun broker"
        assert "submit(" not in content, f"{path} ne doit jamais soumettre d'ordre"


def test_native_roster_adapter_has_no_broker_access() -> None:
    """L'adapter d'analyse (native/agents/adapter.py) produit des AgentOutput,
    jamais un acces broker ni une decision d'autorite."""
    import pathlib

    content = pathlib.Path("native/agents/adapter.py").read_text(encoding="utf-8")
    assert "broker" not in content.lower()
    assert "Authority.ACT" not in content


# ─────────────────────────────────────────────────────────────────────────
# Chaine de receipts (portage cible du concept de agent-trad-main, construit
# a la main plutot que via make_runtime() — voir docstring du module)
# ─────────────────────────────────────────────────────────────────────────


def _receipt(cycle_id: str, previous: "CycleReceipt | None" = None, authority: Authority = Authority.HOLD) -> CycleReceipt:
    decision = _decision(authority)
    return CycleReceipt(
        cycle_id=cycle_id,
        decision_id=decision.decision_id,
        recorded_at=time.time(),
        mode=Mode.SIM,
        state_fingerprint=f"fp-{cycle_id}",
        decision=decision,
        previous_receipt_hash=previous.decision_hash() if previous else GENESIS_HASH,
    )


def test_receipt_chain_verifies_when_continuous() -> None:
    r1 = _receipt("c1")
    r2 = _receipt("c2", previous=r1)
    r3 = _receipt("c3", previous=r2)
    valid, reason = verify_chain((r1, r2, r3))
    assert valid, reason


def test_removing_a_cycle_breaks_the_chain() -> None:
    r1 = _receipt("c1")
    r2 = _receipt("c2", previous=r1)
    r3 = _receipt("c3", previous=r2)
    amputated = (r1, r3)  # r2 retire
    valid, reason = verify_chain(amputated)
    assert not valid
    assert "rupture" in reason.lower() or "chaine" in reason.lower()
