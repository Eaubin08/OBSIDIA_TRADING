"""
apps/cockpit/app.py — F9. Rendu Streamlit, deliberement fin.

Ce fichier ne fait QUE de l'affichage : toute la logique d'assemblage vit
dans presenter.py / scenarios.py, testee independamment du rendu visuel
(voir tests/unit/test_cockpit.py). Lancer avec :

    streamlit run apps/cockpit/app.py

Aucune cle live, aucune connexion reseau reelle : tous les scenarios
utilisent des doubles PAPER-only (apps/cockpit/demo_doubles.py).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from apps.cockpit.presenter import build_cockpit_view, build_replay_view
from apps.cockpit.scenarios import SCENARIOS, run_scenario, scenario_by_key
from proof.receipts.receipt_store import ReceiptStore

st.set_page_config(page_title="Obsidia Trading — Cockpit (F9)", layout="wide")

if "cockpit_store_path" not in st.session_state:
    st.session_state.cockpit_store_path = Path(tempfile.mkdtemp(prefix="obsidia_cockpit_")) / "cockpit_demo_receipts.jsonl"
if "cycle_history" not in st.session_state:
    st.session_state.cycle_history = []  # [(label, cycle_id), ...] pour le scenario Replay

store = ReceiptStore(st.session_state.cockpit_store_path)

st.title("Obsidia Trading — Cockpit (F9)")
st.caption(
    "Projection observable de la stack F1→F8.7 déjà prouvée. "
    "Le Cockpit n'a AUCUNE autorité : il affiche ce que KX108GovernanceBridge, "
    "ExecutionPlanner et ReceiptStore ont déjà produit."
)

st.markdown(
    "```\nMarket/External Input → Source Provenance → Native ou External cognition\n"
    "→ Canonical Contract → Simulation/Evidence → TradeIntent → Governance Bridge\n"
    "→ KX108 Decision → Binder Permission → PAPER Execution → Receipt → Proof/Replay\n```"
)

st.warning(f"⚠️ {('TEST FIXTURE — NOT REAL KX108')} — aucun Kernel X-108 réel n'est branché à ce Cockpit.")

labels = [f"{s.label}" for s in SCENARIOS] + ["8. Replay d'un cycle précédent"]
choice = st.selectbox("Scénario", labels)

if choice.startswith("8."):
    st.subheader("Replay — REPLAY ≠ EXECUTION")
    if not st.session_state.cycle_history:
        st.info("Exécutez d'abord un des scénarios 1 à 7 pour avoir un cycle à rejouer.")
    else:
        pick = st.selectbox(
            "Cycle à rejouer",
            [f"{label}  ({cid})" for label, cid in st.session_state.cycle_history],
        )
        cid = pick.split("(")[-1].rstrip(")")
        if st.button("Lancer le replay (aucun appel broker)"):
            view = build_replay_view(store, cid)
            st.success(view["banner"])
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Audit Replay**")
                st.json(view["audit"])
            with col2:
                st.markdown("**Deterministic Replay**")
                st.write(f"Verdict : `{view['deterministic']['verdict']}`")
                st.json(view["deterministic"])
else:
    spec = next(s for s in SCENARIOS if choice.startswith(s.label))
    st.subheader(spec.label)
    st.write(spec.description)
    mode_label = "🟦 Native" if spec.mode == "native" else "🟨 External"
    st.caption(f"Chemin : {mode_label} — converge vers le **même** Canonical Contract avant gouvernance.")

    if st.button("Exécuter ce cycle (PAPER only)"):
        outcome = run_scenario(spec, store)
        view = build_cockpit_view(outcome, store)
        st.session_state.cycle_history.append((spec.label, outcome.cycle_id))

        st.markdown("### 1. Input")
        st.json(view["input"])

        st.markdown("### 2. Domain State")
        st.json(view["domain_state"])

        st.markdown(f"### 3. Agents ({view['agents']['count']} exécutés)")
        st.json(view["agents"])

        st.markdown("### 4. Simulation")
        st.info(view["simulation"]["banner"])
        st.json(view["simulation"])

        st.markdown("### 5. Intent")
        st.info(view["intent"]["banner"])
        st.json(view["intent"])

        st.markdown("### 6. Governance")
        st.json(view["governance"])

        st.markdown("### 7. KX108")
        st.error(view["kx108"]["banner"])
        st.write(f"Autorité : `{view['kx108']['authority']}`")
        st.json(view["kx108"])

        st.markdown("### 8. Binder")
        st.info(view["binder"]["banner"])
        col1, col2 = st.columns(2)
        col1.metric("KX108 Decision", view["binder"]["kx108_decision"] or "—")
        col2.metric("Binder Permission", "ALLOW" if view["binder"]["binder_permission_granted"] else "REFUSED")

        st.markdown("### 9. Execution (PAPER)")
        st.json(view["execution"])

        st.markdown("### 10. Receipt / Proof")
        st.json(view["receipt"])

        st.markdown("### 11. Replay (audit immédiat, zéro effet de bord)")
        st.json(view["replay"])
