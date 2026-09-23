"""
apps/cockpit_v2/app.py — Cockpit V2 Phase A. Rendu Streamlit, délibérément fin.

Trois espaces clairement séparés : REFERENCE RUNTIME (vrai Kernel, PAPER,
PROOF_REQUIRED) — GUIDED DEMO (F9, FixtureKX108Client, inchangé) —
NAIVE VS GOVERNED (contrefactuel pédagogique, inchangé).

Lancer avec : streamlit run apps/cockpit_v2/app.py
(ou scripts/run_cockpit.ps1 pour l'onboarding sans PYTHONPATH manuel).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from apps.cockpit.naive_vs_governed_view import render_naive_vs_governed
from apps.cockpit_v2 import guided_demo_view
from apps.cockpit_v2.reference_runtime_presenter import build_error_view, build_human_view
from apps.cockpit_v2.reference_runtime_view import reference_runtime_status, run_reference_cycle
from proof.receipts.receipt_store import ReceiptStore

st.set_page_config(page_title="Obsidia Trading — Cockpit V2", layout="wide")

if "cockpit_v2_demo_store_path" not in st.session_state:
    st.session_state.cockpit_v2_demo_store_path = Path(tempfile.mkdtemp(prefix="obsidia_cockpit_v2_demo_")) / "demo_receipts.jsonl"
demo_store = ReceiptStore(st.session_state.cockpit_v2_demo_store_path)

if "cockpit_v2_kx108_observed" not in st.session_state:
    st.session_state.cockpit_v2_kx108_observed = None  # None | "CONNECTED" | "UNAVAILABLE"

st.title("Obsidia Trading — Cockpit V2")

space = st.sidebar.radio(
    "Espace",
    ["REFERENCE RUNTIME", "GUIDED DEMO", "NAIVE VS GOVERNED"],
    index=0,  # Reference Runtime = vue par défaut (Phase A1)
)

if space == "GUIDED DEMO":
    st.caption("Espace historique F9 — réutilisé sans modification.")
    guided_demo_view.render(demo_store)

elif space == "NAIVE VS GOVERNED":
    st.warning("COUNTERFACTUAL / PEDAGOGICAL — côté « gouverné » basé sur FixtureKX108Client dans cette démo.")
    render_naive_vs_governed(demo_store)

else:  # REFERENCE RUNTIME
    st.markdown(
        "```\nReal Market → Native cognition (17 agents calibrés F13.1) → Canonical Contract\n"
        "→ Governance Bridge → REAL KX108 (RealKX108Client, F12) → Binder → PAPER Execution\n"
        "→ Receipt (ProofPolicy.REQUIRED, F11) → Proof/Replay\n```"
    )
    st.info(
        "Aucune décision n'est recalculée ici : cette page projette ce que "
        "CycleEngine/KX108GovernanceBridge/ReceiptStore ont réellement produit."
    )

    symbol = st.text_input("Symbole", value="AAPL", key="reference_runtime_symbol")
    status = reference_runtime_status(st.session_state.cockpit_v2_kx108_observed)

    st.subheader("Runtime Status")
    cols = st.columns(4)
    cols[0].metric("Source", "Native")
    cols[1].metric("Market", "Alpaca paper")
    cols[2].metric("KX108", status["kx108"])
    cols[3].metric("Mode", status["mode"])
    cols2 = st.columns(4)
    cols2[0].metric("Proof", status["proof"])
    cols2[1].metric("Binder", "ACTIVE")
    cols2[2].metric("Execution", "PAPER ONLY")
    cols2[3].metric("Receipt", "ReceiptStore")
    if status["kx108"] == "NOT CONFIGURED":
        st.error("Identifiants Alpaca absents de l'environnement (.env) — le cycle échouera en configuration, pas en fail-closed silencieux.")
    with st.expander("Détails du statut (technique)"):
        st.json(status)

    if st.button("Lancer un cycle réel (PAPER only)", key="reference_runtime_run"):
        result = run_reference_cycle(symbol)
        if not result["ok"]:
            st.session_state.cockpit_v2_kx108_observed = (
                "UNAVAILABLE" if result["error_kind"] == "KX108Unavailable" else st.session_state.cockpit_v2_kx108_observed
            )
            st.error(f"Cycle non complété : {result['error_kind']}")
            st.json(build_error_view(result["error_kind"], result["error_message"]))
        else:
            st.session_state.cockpit_v2_kx108_observed = "CONNECTED"
            view = build_human_view(result["outcome"], result["store"])

            st.markdown("### A. Situation")
            st.json(view["A_situation"])
            st.markdown("### B. Trading cognition")
            st.json(view["B_cognition"])
            st.markdown("### C. Proposal")
            st.json(view["C_proposal"])
            st.markdown("### D. Governance (REAL KX108)")
            st.json(view["D_governance"])
            st.markdown("### E. Permission")
            st.info(view["E_permission"]["banner"])
            st.write(f"Binder : `{view['E_permission']['binder_permission']}`")
            st.markdown("### F. Execution (PAPER)")
            st.json(view["F_execution"])
            st.markdown("### G. Proof")
            st.json(view["G_proof"])
            with st.expander("Voir détails techniques"):
                st.json(view["technical"])
