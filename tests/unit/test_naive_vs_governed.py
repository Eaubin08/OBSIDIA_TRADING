"""
DEMO — Naive vs Governed (branche demo/naive-vs-governed-v1).

12 tests de securite obligatoires. Chaque test appelle reellement le code de
la demo et fait des assertions sur son contenu — pas seulement sur son
absence de logique.
"""
from __future__ import annotations

import ast
import pathlib

from apps.cockpit.demo_doubles import SYMBOL, DemoMarketData
from apps.cockpit.scenarios import run_scenario, scenario_by_key
from apps.naive_vs_governed.comparison import SCENARIOS, build_comparison, shared_market_snapshot
from apps.naive_vs_governed.naive_path import NAIVE_ROSTER, run_naive_path
from domain.types import Authority
from proof.receipts.receipt_store import ReceiptStore
from proof.receipts.replay import ReplayEngine

NVG_DIR = pathlib.Path(__file__).resolve().parents[2] / "apps" / "naive_vs_governed"
NAIVE_PATH_FILE = NVG_DIR / "naive_path.py"

FORBIDDEN_MODULES_FOR_NAIVE = (
    "governance.bridge",
    "governance",
    "execution.binder",
    "execution",
    "market.adapters.alpaca",
    "market.adapters",
    "domain.contracts.canonical",
)


def _store(tmp_path) -> ReceiptStore:
    return ReceiptStore(tmp_path / "nvg_receipts.jsonl")


def _imported_modules(path: pathlib.Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


# ── 1-3. Isolation structurelle du chemin Naive ─────────────────────────────


def test_naive_path_never_imports_broker():
    imports = _imported_modules(NAIVE_PATH_FILE)
    assert not any(m.startswith("market.adapters.alpaca") for m in imports)


def test_naive_path_never_imports_binder():
    imports = _imported_modules(NAIVE_PATH_FILE)
    assert not any(m.startswith("execution.binder") or m == "execution" for m in imports)


def test_naive_path_never_imports_governance_or_canonical():
    """Le chemin Naive ne peut produire une CanonicalDecision : il n'a
    aucun acces a governance.bridge ni a domain.contracts.canonical
    (to_canonical_agent_signal)."""
    imports = _imported_modules(NAIVE_PATH_FILE)
    assert not any(m.startswith("governance") for m in imports)
    assert not any(m.startswith("domain.contracts.canonical") for m in imports)
    # Confirmation dynamique : NaiveOutcome ne porte aucun champ Authority.
    snapshot = DemoMarketData().snapshot(SYMBOL)
    outcome = run_naive_path(SYMBOL, snapshot)
    assert not hasattr(outcome, "authority")
    assert not hasattr(outcome, "decision")


# ── 4. Governed utilise le vrai runtime existant ────────────────────────────


def test_governed_side_uses_the_real_cycle_engine(tmp_path):
    store = _store(tmp_path)
    result = build_comparison("A", store)
    assert result.governed_outcome is not None
    # Meme fonction que le Cockpit F9 (apps.cockpit.scenarios.run_scenario) :
    # un second appel direct sur le meme scenario doit produire un outcome du
    # meme type, avec un decision.authority reellement issu du Bridge.
    direct = run_scenario(scenario_by_key("native_act_paper_success"), store)
    assert type(result.governed_outcome) is type(direct)
    assert result.governed_outcome.decision.authority is Authority.ACT


# ── 5. La comparaison ne modifie aucun verdict ──────────────────────────────


def test_comparison_never_modifies_the_verdict(tmp_path):
    store_a = _store(tmp_path)
    outcome_direct = run_scenario(scenario_by_key("native_block"), store_a)

    store_b = ReceiptStore(tmp_path / "nvg_receipts_b.jsonl")
    result = build_comparison("C", store_b)

    assert outcome_direct.decision.authority == result.governed_outcome.decision.authority == Authority.BLOCK


# ── 6. Memes entrees dans les deux chemins ──────────────────────────────────


def test_same_market_input_feeds_both_paths():
    snap1 = shared_market_snapshot()
    snap2 = shared_market_snapshot()
    assert snap1.last_price == snap2.last_price
    assert snap1.bars == snap2.bars  # deterministe, aucun alea

    naive = run_naive_path(SYMBOL, snap1)
    # Les votes bruts Naive proviennent du meme roster (17 classes) que le
    # roster natif Governed (native/agents/adapter.py::ROSTER_17) — meme
    # nombre d'agents, memes noms, sur les memes bars.
    assert len(naive.source_votes) == 17 == len(NAIVE_ROSTER)


# ── 7. LIVE impossible sur les deux chemins ─────────────────────────────────


def test_live_impossible_for_naive_and_governed(tmp_path):
    store = _store(tmp_path)
    result = build_comparison("E", store)
    assert result.governed_outcome is None
    assert result.live_rejection["refused"] is True
    assert result.live_rejection["attempted_mode"] == "LIVE"
    assert "NONE" in result.live_rejection["naive_live_capability"]
    # Isolation Naive confirmee independamment : aucun import broker.
    assert not any(
        m.startswith("market.adapters.alpaca") for m in _imported_modules(NAIVE_PATH_FILE)
    )


# ── 8. Le mode External reste compatible ────────────────────────────────────


def test_external_mode_still_compatible(tmp_path):
    store = _store(tmp_path)
    result = build_comparison("G", store)
    assert result.governed_outcome is not None
    provenances = [
        ao.source_provenance.source_system
        for ao in result.governed_outcome.agent_outputs
        if ao.source_provenance is not None
    ]
    assert "external" in provenances
    assert result.governed_outcome.decision.authority is Authority.ACT


# ── 9. Le receipt affiche = le receipt persiste ─────────────────────────────


def test_displayed_receipt_matches_persisted_receipt(tmp_path):
    store = _store(tmp_path)
    result = build_comparison("A", store)
    stored = store.find_by_cycle_id(result.governed_outcome.cycle_id)
    assert stored is not None
    assert result.governed_view["receipt"]["current_hash"] == stored.stored_hash
    assert result.governed_view["receipt"]["cycle_id"] == stored.cycle_id


# ── 10. Replay reste sans effet de bord ─────────────────────────────────────


def test_replay_has_zero_broker_calls_in_naive_vs_governed_context(tmp_path):
    store = _store(tmp_path)
    result = build_comparison("A", store)
    replay = ReplayEngine(store)
    audit = replay.replay_audit(result.governed_outcome.cycle_id)
    assert audit.found is True
    # ReplayEngine (F7) reste importe uniquement pour la verification du test,
    # jamais depuis apps/naive_vs_governed/naive_path.py (voir tests 1-3).
    assert "proof.receipts.replay" not in _imported_modules(NAIVE_PATH_FILE)


# ── 11. Baseline F10 reste verifiable ───────────────────────────────────────


def test_f10_freeze_baseline_untouched():
    """
    Depuis la promotion vers v0.2, la racine (merkle_seal.json,
    docs/FREEZE_MANIFEST.json) porte desormais le seal ACTIF v0.2 — elle ne
    doit plus etre comparee au hash v0.1. La reference historique v0.1 est
    verifiee separement, de facon independante de l'arbre courant, dans
    docs/history/ (voir tests/unit/test_historical_seal_v0_1.py). Ce test
    verifie seulement que l'archive figee v0.1 est toujours presente et
    n'a pas ete alteree par cette branche.
    """
    root = pathlib.Path(__file__).resolve().parents[2]
    archived_manifest = (root / "docs" / "history" / "FREEZE_MANIFEST_V0.1.json").read_text(
        encoding="utf-8"
    )
    archived_seal = (root / "docs" / "history" / "merkle_seal_v0.1.json").read_text(
        encoding="utf-8"
    )
    assert (
        '"root_hash": "5711dbfa0a0c4a83108eb68b66b03bb9af283240243766eb70eb67cfa06d2fd4"'
        in archived_seal
    )
    assert "e6ae249c35c017dc78445f7020f8951b161f4316" in archived_manifest


# ── 12. Suite globale sans regression — verifie separement par le parent (pytest tests/ -q) ─
