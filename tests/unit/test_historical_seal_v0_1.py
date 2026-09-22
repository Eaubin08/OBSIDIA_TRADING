"""Verifie que le freeze historique v0.1 (commit 9e68391) reste
reproductible independamment de l'etat courant de l'arbre (desormais v0.2).

Ce test ne depend JAMAIS du contenu courant des fichiers sur disque : il
relit le contenu exact tel qu'il existait au commit 9e68391 via
`git show <commit>:<path>`, recalcule le root_hash a partir de ce contenu
historique, et le compare au seal archive dans docs/history/. Un mensonge
sur l'histoire du freeze v0.1 (contenu du commit 9e68391 modifie) ferait
echouer ce test independamment de tout changement fait par v0.2.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HISTORY_DIR = REPO_ROOT / "docs" / "history"
V01_COMMIT = "9e68391"


def _git_show(commit: str, rel_path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}:{rel_path}"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    )
    return result.stdout


def test_v0_1_archive_files_exist():
    assert (HISTORY_DIR / "FREEZE_MANIFEST_V0.1.json").exists()
    assert (HISTORY_DIR / "FREEZE_MANIFEST_V0.1.md").exists()
    assert (HISTORY_DIR / "merkle_seal_v0.1.json").exists()
    assert (HISTORY_DIR / "seal_v0.1_pairs.json").exists()


def test_v0_1_archived_manifest_and_seal_are_byte_identical_to_commit():
    """Les copies figees dans docs/history/ ne doivent jamais deriver du
    contenu reel du commit 9e68391 — meme s'il n'est plus HEAD."""
    archived_manifest = (HISTORY_DIR / "FREEZE_MANIFEST_V0.1.json").read_bytes()
    archived_seal = (HISTORY_DIR / "merkle_seal_v0.1.json").read_bytes()

    assert archived_manifest == _git_show(V01_COMMIT, "docs/FREEZE_MANIFEST.json")
    assert archived_seal == _git_show(V01_COMMIT, "merkle_seal.json")


def test_v0_1_root_hash_is_reproducible_from_git_history_alone():
    """Recalcule le root_hash v0.1 a partir du contenu du commit 9e68391 lu
    directement via git (jamais depuis le disque courant, qui porte v0.2),
    et le compare au seal archive."""
    archive = json.loads((HISTORY_DIR / "seal_v0.1_pairs.json").read_text(encoding="utf-8"))
    seal_v01 = json.loads((HISTORY_DIR / "merkle_seal_v0.1.json").read_text(encoding="utf-8"))

    recomputed_pairs = []
    for rel_path, _archived_hash in archive["pairs"]:
        content = _git_show(V01_COMMIT, rel_path)
        recomputed_pairs.append([rel_path, hashlib.sha256(content).hexdigest()])
    recomputed_pairs.sort(key=lambda pair: pair[0])

    canonical = json.dumps(recomputed_pairs, sort_keys=True, separators=(",", ":"))
    recomputed_root_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    assert len(recomputed_pairs) == 83 == seal_v01["sealed_file_count"]
    assert recomputed_root_hash == seal_v01["root_hash"]
    assert recomputed_root_hash == archive["root_hash"]
    assert recomputed_root_hash == (
        "5711dbfa0a0c4a83108eb68b66b03bb9af283240243766eb70eb67cfa06d2fd4"
    )


def test_v0_1_commit_still_reachable_in_history():
    """9e68391 doit rester un ancetre atteignable de HEAD : la promotion vers
    v0.2 ne doit jamais reecrire ou detacher l'historique v0.1."""
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", V01_COMMIT, "HEAD"],
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, (
        f"{V01_COMMIT} (freeze v0.1) n'est plus un ancetre de HEAD : "
        "l'historique a ete reecrit, ce qui est interdit."
    )
