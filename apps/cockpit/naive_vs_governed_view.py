"""
apps/cockpit/naive_vs_governed_view.py — DEMO (branche demo/naive-vs-governed-v1).

Rendu Streamlit, deliberement fin : toute la logique vit dans
apps/naive_vs_governed/{naive_path,comparison}.py, testee independamment du
rendu (tests/unit/test_naive_vs_governed.py). Ce fichier ne calcule rien —
il affiche ce que ComparisonResult contient deja.

UI != Authority : aucune ligne ici ne fabrique un verdict ACT/HOLD/BLOCK ni
une permission Binder.
"""
from __future__ import annotations

import streamlit as st

from apps.naive_vs_governed.comparison import SCENARIOS, ComparisonResult, build_comparison
from proof.receipts.receipt_store import ReceiptStore


def render_naive_vs_governed(store: ReceiptStore) -> None:
    st.subheader("Naive vs Governed")
    st.caption(
        "Meme entree exacte (memes bars de marche synthetiques deterministes, "
        "meme roster d'agents) comparee sur deux chemins : "
        "NAIVE = COUNTERFACTUAL DEMO (aucune gouvernance, jamais executable) et "
        "GOVERNED (le vrai pipeline F1-F8.7 : CycleEngine → GovernanceBridge → "
        "KX108 → Binder → PAPER Execution → Receipt)."
    )
    st.warning("⚠️ TEST FIXTURE — NOT REAL KX108 — aucun Kernel X-108 réel n'est branché.")
    st.info("PAPER ONLY — aucun ordre live n'est possible sur aucun des deux chemins.")

    letters = [f"{s.letter}. {s.title}" for s in SCENARIOS]
    choice = st.selectbox("Scénario Naive vs Governed", letters, key="nvg_scenario")
    letter = choice.split(".")[0]

    result: ComparisonResult = build_comparison(letter, store)
    st.markdown(f"**Narratif** — {result.scenario.narrative}")

    col_naive, col_governed = st.columns(2)

    with col_naive:
        st.markdown(f"### {result.labels['naive']}")
        n = result.naive
        st.metric("Signal dominant", n.dominant_signal)
        st.write("Votes bruts (17 agents) :", dict(n.vote_counts))
        st.write("Action candidate :", n.candidate_action)
        st.write("Exposition prédite :", f"{n.predicted_exposure:.2f}")
        st.caption(n.predicted_risk_note)
        st.caption(n.simulated_result_note)
        if n.ignored_unknowns:
            st.error(f"Unknowns ignorés par Naive : {n.ignored_unknowns}")
        if n.ignored_contradictions:
            st.error(f"Contradictions ignorées par Naive : {n.ignored_contradictions}")
        if n.ignored_risk_flags:
            st.error(f"Risk flags ignorés par Naive : {n.ignored_risk_flags}")

    with col_governed:
        st.markdown(f"### GOVERNED — {result.labels['kx108_fixture']}")
        if result.live_rejection is not None:
            lr = result.live_rejection
            st.write("Tentative de mode :", lr["attempted_mode"])
            st.write("Refusé structurellement :", lr["refused"])
            st.write("Détail :", lr["detail"])
            st.write("Mécanisme réutilisé :", lr["mechanism"])
            st.write("Capacité live côté Naive :", lr["naive_live_capability"])
        else:
            v = result.governed_view
            st.write("Unknowns (Domain State) :", v["domain_state"]["unknowns"])
            st.write("Contradictions :", v["domain_state"]["contradictions"])
            st.write("Risk flags :", v["domain_state"]["risk_flags"])
            st.write("Simulation Evidence — SIMULATION ≠ AUTHORITY :", v["simulation"])
            st.write("Intent — INTENT ≠ ACTION :", v["intent"])
            st.write("KX108 Decision :", v["kx108"])
            st.write("Binder Permission — DECISION ≠ PERMISSION :", v["binder"])
            st.write("Execution Result :", v["execution"])
            st.write("Receipt :", v["receipt"])

    st.caption(f"labels: {result.labels}")
