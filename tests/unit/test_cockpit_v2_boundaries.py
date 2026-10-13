"""
Cockpit V2 Phase A9 — frontières structurelles.

UI != Authority / Governance / Binder / Execution. Aucune de ces propriétés
n'est vérifiée par confiance : chaque test lit le code source réel (AST) ou
exécute le vrai chemin d'assemblage.
"""
from __future__ import annotations

import ast
import pathlib
import subprocess

import pytest

COCKPIT_V2_DIR = pathlib.Path(__file__).resolve().parents[2] / "apps" / "cockpit_v2"
LEGACY_COCKPIT_TEST = pathlib.Path(__file__).resolve().parent / "test_cockpit.py"


def _modules():
    return list(COCKPIT_V2_DIR.glob("*.py"))


def test_no_fixture_kx108_client_import_in_v2_package():
    """
    Le chemin Reference Runtime ne doit jamais importer FixtureKX108Client
    (reserve a tests/test_support/, TEST-ONLY). guided_demo_view.py importe
    des composants F9 (Fixture par construction) : exclu de cette regle,
    car c'est precisement l'espace GUIDED DEMO, explicitement labellise.
    """
    for path in _modules():
        if path.name == "guided_demo_view.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                src = ast.dump(node)
                assert "FixtureKX108Client" not in src, f"{path.name} importe FixtureKX108Client"
                assert "test_support" not in (getattr(node, "module", "") or ""), f"{path.name} importe depuis tests/test_support"


def test_reference_runtime_view_uses_real_kx108_client_and_proof_required():
    """Test structurel : le point d'assemblage utilise bien RealKX108Client + ProofPolicy.REQUIRED."""
    src = (COCKPIT_V2_DIR / "reference_runtime_view.py").read_text(encoding="utf-8")
    assert "RealKX108Client" in src
    assert "ProofPolicy.REQUIRED" in src


def test_no_authority_value_assignment_in_v2_package():
    """Aucune affectation directe Authority.ACT/HOLD/BLOCK dans apps/cockpit_v2/*.py."""
    for path in _modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    name = getattr(target, "id", None) or getattr(target, "attr", None)
                    if name == "authority":
                        value_src = ast.dump(node.value)
                        assert "Authority.ACT" not in value_src
                        assert "Authority.HOLD" not in value_src
                        assert "Authority.BLOCK" not in value_src


def test_no_direct_broker_or_binder_import_in_presenter():
    """presenter.py est une couche de projection : aucun import broker/binder direct."""
    src = (COCKPIT_V2_DIR / "reference_runtime_presenter.py").read_text(encoding="utf-8")
    assert "market.adapters.alpaca" not in src
    assert "execution.binder.paper_execution" not in src


def test_no_kx108_decision_formula_in_ui():
    """Aucun calcul de T_mean/H_score/A_score/S/theta_S dans apps/cockpit_v2/*.py — lecture seule uniquement."""
    for path in _modules():
        src = path.read_text(encoding="utf-8")
        for forbidden in ("T_mean", "H_score", "A_score", "theta_S", "structural_score ="):
            assert forbidden not in src, f"{path.name} contient une formule de decision ({forbidden})"


def test_legacy_f9_cockpit_files_untouched_by_this_branch():
    """
    Garde-fou de non-regression : les fichiers F9 existants restent
    identiques a leur contenu attendu (import/API stable) — verifie
    indirectement en relancant la suite de tests F9 deja existante.
    """
    result = subprocess.run(
        ["python", "-m", "pytest", str(LEGACY_COCKPIT_TEST), "-q"],
        cwd=str(pathlib.Path(__file__).resolve().parents[2]),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
