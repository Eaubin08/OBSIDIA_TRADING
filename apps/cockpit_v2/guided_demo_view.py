"""
apps/cockpit_v2/guided_demo_view.py — Cockpit V2 Phase A4.

Wrapper fin autour des composants F9 existants (apps/cockpit/presenter.py,
apps/cockpit/scenarios.py), SANS AUCUNE MODIFICATION de apps/cockpit/*.py.
Labellise explicitement cet espace comme GUIDED DEMO — FixtureKX108Client —
scénarios pédagogiques déterministes — jamais présenté comme le Reference
Runtime réel.
"""
from __future__ import annotations

import streamlit as st

from apps.cockpit.presenter import build_cockpit_view, build_replay_view
from apps.cockpit.scenarios import SCENARIOS, run_scenario
from proof.receipts.receipt_store import ReceiptStore

GUIDED_DEMO_BANNER = (
    "GUIDED DEMO — FixtureKX108Client — scénarios pédagogiques déterministes — "
    "PAS le Reference Runtime. Ses verdicts ne proviennent JAMAIS du vrai Kernel."
)


def render(store: ReceiptStore) -> None:
    st.warning(GUIDED_DEMO_BANNER)
    if "cockpit_v2_cycle_history" not in st.session_state:
        st.session_state.cockpit_v2_cycle_history = []

    labels = [s.label for s in SCENARIOS] + ["8. Replay d'un cycle précédent"]
    choice = st.selectbox("Scénario (Guided Demo)", labels, key="guided_demo_scenario")

    if choice.startswith("8."):
        if not st.session_state.cockpit_v2_cycle_history:
            st.info("Exécutez d'abord un scénario 1 à 7 pour avoir un cycle à rejouer.")
            return
        pick = st.selectbox(
            "Cycle à rejouer",
            [f"{label}  ({cid})" for label, cid in st.session_state.cockpit_v2_cycle_history],
            key="guided_demo_replay_pick",
        )
        cid = pick.split("(")[-1].rstrip(")")
        if st.button("Lancer le replay (aucun appel broker)", key="guided_demo_replay_btn"):
            view = build_replay_view(store, cid)
            st.success(view["banner"])
            st.json(view)
        return

    spec = next(s for s in SCENARIOS if choice == s.label)
    st.write(spec.description)
    if st.button("Exécuter ce scénario (PAPER only)", key="guided_demo_run_btn"):
        outcome = run_scenario(spec, store)
        view = build_cockpit_view(outcome, store)
        st.session_state.cockpit_v2_cycle_history.append((spec.label, outcome.cycle_id))
        with st.expander("Voir détails techniques (11 sections F9)", expanded=True):
            st.json(view)
