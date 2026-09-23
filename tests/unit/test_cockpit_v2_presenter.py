"""
Cockpit V2 Phase A9 — couche de données de reference_runtime_presenter.py.

Réutilise un CycleOutcome produit par le scénario F9 existant (fixture,
déterministe) pour vérifier la FORME et l'HONNÊTETÉ de la projection, sans
jamais exiger de vrai Kernel réseau dans un test unitaire.
"""
from __future__ import annotations

from apps.cockpit.scenarios import run_scenario, scenario_by_key
from apps.cockpit_v2.reference_runtime_presenter import build_error_view, build_human_view
from proof.receipts.receipt_store import ReceiptStore


def _store(tmp_path) -> ReceiptStore:
    return ReceiptStore(tmp_path / "v2_presenter_receipts.jsonl")


def test_human_view_authority_matches_decision_exactly(tmp_path):
    store = _store(tmp_path)
    outcome = run_scenario(scenario_by_key("native_act_paper_success"), store)
    view = build_human_view(outcome, store)
    assert view["D_governance"]["x108_decision"] == outcome.decision.authority.value


def test_human_view_preserves_unknowns_contradictions_risk_flags(tmp_path):
    store = _store(tmp_path)
    outcome = run_scenario(scenario_by_key("native_hold_unknown_critical"), store) if _has(
        "native_hold_unknown_critical"
    ) else run_scenario(scenario_by_key("native_act_paper_success"), store)
    view = build_human_view(outcome, store)
    expected_unknowns = [u for ao in outcome.agent_outputs for u in ao.unknowns]
    expected_contradictions = [c for ao in outcome.agent_outputs for c in ao.contradictions]
    expected_risk_flags = [r for ao in outcome.agent_outputs for r in ao.risk_flags]
    assert view["B_cognition"]["unknowns"] == expected_unknowns
    assert view["B_cognition"]["contradictions"] == expected_contradictions
    assert view["B_cognition"]["risk_flags"] == expected_risk_flags


def _has(scenario_id: str) -> bool:
    try:
        scenario_by_key(scenario_id)
        return True
    except Exception:
        return False


def test_technical_section_preserves_raw_agent_outputs(tmp_path):
    store = _store(tmp_path)
    outcome = run_scenario(scenario_by_key("native_act_paper_success"), store)
    view = build_human_view(outcome, store)
    assert view["technical"]["agents"]["count"] == len(outcome.agent_outputs)
    assert view["technical"]["agents"]["outputs"] == [ao.as_dict() for ao in outcome.agent_outputs]


def test_technical_section_preserves_raw_receipt_when_persisted(tmp_path):
    store = _store(tmp_path)
    outcome = run_scenario(scenario_by_key("native_act_paper_success"), store)
    view = build_human_view(outcome, store)
    stored = store.find_by_cycle_id(outcome.cycle_id)
    if stored is not None:
        assert view["technical"]["receipt_raw"] == stored.raw


def test_proposal_absent_when_no_strategy_wired(tmp_path):
    """
    Ce repo n'a aucune StrategyPort/SizingPort reelle (voir
    reference_runtime_view.py docstring) : quand un scenario n'a pas
    selectionne de strategie, C_proposal doit rester honnete (action
    explicite, jamais une valeur inventee).
    """
    store = _store(tmp_path)
    outcome = run_scenario(scenario_by_key("native_act_paper_success"), store)
    view = build_human_view(outcome, store)
    if outcome.proposal is None:
        assert "AUCUNE" in view["C_proposal"]["action"]


def test_error_view_never_claims_success():
    view = build_error_view("KX108Unavailable", "Kernel injoignable")
    assert view["ok"] is False
    assert view["error_kind"] == "KX108Unavailable"
    assert "AUCUNE EXÉCUTION" in view["banner"]
