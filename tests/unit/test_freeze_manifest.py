"""Verifie que le manifest de freeze et le merkle seal sont coherents.

Ce test ne juge pas l'opportunite du freeze (decision humaine) : il verifie
seulement que les artefacts produits sont parseables et que le root_hash du
seal est effectivement recalculable a partir des fichiers qu'il pretend
couvrir. Un fichier modifie apres scellement doit faire echouer ce test.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from compute_seal import collect_sealed_files, compute_root_hash  # noqa: E402


def test_freeze_manifest_json_exists_and_is_parseable():
    manifest_path = REPO_ROOT / "docs" / "FREEZE_MANIFEST.json"
    assert manifest_path.exists(), "docs/FREEZE_MANIFEST.json est absent"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key in (
        "project",
        "freeze_version",
        "git_commit",
        "test_count",
        "skipped_count",
        "architecture_status",
        "native_path_status",
        "external_path_status",
        "canonical_contract_version",
        "receipt_schema_version",
        "proof_policy",
        "paper_only_status",
        "kx108_status",
        "known_debts",
        "known_boundaries",
    ):
        assert key in data, f"champ manquant dans FREEZE_MANIFEST.json: {key}"
    assert data["project"] == "OBSIDIA_TRADING"
    assert isinstance(data["known_debts"], list) and data["known_debts"], (
        "known_debts ne doit jamais etre vide ou absent : un freeze ne cache "
        "pas ses dettes"
    )


def test_freeze_manifest_markdown_exists():
    md_path = REPO_ROOT / "docs" / "FREEZE_MANIFEST.md"
    assert md_path.exists(), "docs/FREEZE_MANIFEST.md est absent"
    content = md_path.read_text(encoding="utf-8")
    assert "Dettes connues" in content or "dettes" in content.lower()


def test_merkle_seal_exists_and_root_hash_is_recomputable():
    seal_path = REPO_ROOT / "merkle_seal.json"
    assert seal_path.exists(), "merkle_seal.json (OBSIDIA_TRADING) est absent"
    seal = json.loads(seal_path.read_text(encoding="utf-8"))

    for key in ("root_hash", "hash_algorithm", "commit", "sealed_file_count"):
        assert key in seal, f"champ manquant dans merkle_seal.json: {key}"
    assert seal["hash_algorithm"] == "SHA-256"
    assert len(seal["root_hash"]) == 64, "root_hash doit etre un SHA-256 hex (64 caracteres)"

    files = collect_sealed_files()
    assert seal["sealed_file_count"] == len(files), (
        "le nombre de fichiers scelles a change depuis le calcul du seal "
        "(fichier ajoute/supprime dans le perimetre sans regeneration du seal)"
    )

    recomputed_root_hash, _ = compute_root_hash(files)
    assert recomputed_root_hash == seal["root_hash"], (
        "le root_hash recalcule ne correspond plus au seal : au moins un "
        "fichier du perimetre scelle a ete modifie depuis la generation du "
        "merkle_seal.json (c'est exactement ce que ce test doit detecter)"
    )


def test_merkle_seal_does_not_cover_tests_or_data():
    files = collect_sealed_files()
    rel_paths = {p.relative_to(REPO_ROOT).as_posix() for p in files}
    for rel in rel_paths:
        assert not rel.startswith("tests/"), f"tests/ ne doit pas etre scelle: {rel}"
        assert "__pycache__" not in rel
        assert "proof/receipts/data/" not in rel


def test_seal_scope_document_exists():
    scope_path = REPO_ROOT / "docs" / "SEAL_SCOPE.md"
    assert scope_path.exists(), "docs/SEAL_SCOPE.md (perimetre du seal) est absent"
    content = scope_path.read_text(encoding="utf-8")
    assert "What is sealed" in content
    assert "What is NOT sealed" in content
