"""Calcule et (re)genere merkle_seal.json pour OBSIDIA_TRADING.

Algorithme documente dans docs/SEAL_SCOPE.md. Deterministe : deux executions
sur un contenu identique produisent le meme root_hash. Ne touche jamais au
merkle_seal.json du core Obsidia (hors perimetre de ce script).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SEALED_DIRS = (
    "domain",
    "native",
    "external",
    "market",
    "simulation",
    "governance",
    "execution",
    "proof",
    "apps",
)

SEALED_DOCS = (
    "README.md",
    "docs/B15_STRUCTURAL_SCORE_BOUNDARY.md",
    "docs/MIGRATION_PROVENANCE.md",
    "docs/F10_HISTORICAL_REGRESSION_MATRIX.md",
    "docs/FREEZE_MANIFEST.md",
)

EXCLUDED_PARTS = {"__pycache__", "data"}


def _is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_PARTS for part in path.parts) or path.suffix == ".pyc"


def collect_sealed_files() -> list[Path]:
    files: list[Path] = []
    for dirname in SEALED_DIRS:
        base = REPO_ROOT / dirname
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if path.is_file() and not _is_excluded(path):
                files.append(path)
    for rel in SEALED_DOCS:
        path = REPO_ROOT / rel
        if path.exists():
            files.append(path)
    return sorted(set(files), key=lambda p: p.relative_to(REPO_ROOT).as_posix())


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute_root_hash(files: list[Path]) -> tuple[str, list[list[str]]]:
    pairs = [[p.relative_to(REPO_ROOT).as_posix(), file_hash(p)] for p in files]
    pairs.sort(key=lambda pair: pair[0])
    canonical = json.dumps(pairs, sort_keys=True, separators=(",", ":"))
    root_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return root_hash, pairs


def current_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:
        return "UNKNOWN"


def main() -> None:
    files = collect_sealed_files()
    root_hash, pairs = compute_root_hash(files)
    seal = {
        "status": "INTEGRITY_VERIFIED",
        "project": "OBSIDIA_TRADING",
        "scope_document": "docs/SEAL_SCOPE.md",
        "hash_algorithm": "SHA-256",
        "sealed_file_count": len(pairs),
        "root_hash": root_hash,
        "commit": current_commit(),
        "commit_semantics": (
            "'commit' est le HEAD au moment ou ce script a lu l'arbre de "
            "travail. Un commit ulterieur peut exister sans que le contenu "
            "scelle change (ex: un commit qui enregistre ce fichier lui-meme). "
            "Pour une reference stable, utiliser reference_tag plutot que ce "
            "champ."
        ),
        "reference_tag": "obsidia-trading-v0.2.2-reference",
        "generation_timestamp": datetime.now(timezone.utc).isoformat(),
        "note": (
            "Ce seal couvre uniquement le code de production et les docs de "
            "gouvernance listes dans docs/SEAL_SCOPE.md. Il ne prouve rien sur "
            "le Kernel X-108 reel, ni sur les sources historiques externes."
        ),
    }
    out_path = REPO_ROOT / "merkle_seal.json"
    out_path.write_text(json.dumps(seal, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"merkle_seal.json ecrit : {len(pairs)} fichiers, root_hash={root_hash[:16]}...")


if __name__ == "__main__":
    sys.exit(main() or 0)
