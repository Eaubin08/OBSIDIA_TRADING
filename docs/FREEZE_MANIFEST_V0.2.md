# FREEZE_MANIFEST — OBSIDIA_TRADING v0.2

> Version active. La v0.1 reste archivee, intacte et independamment verifiable
> sous `docs/history/` (voir `docs/history/FREEZE_MANIFEST_V0.1.md` et
> `tests/unit/test_historical_seal_v0_1.py`).

| Champ | Valeur |
|---|---|
| reference_version | v0.2 |
| parent_reference | v0.1 |
| parent_commit | `9e68391da6b5b6c631ae83b7c5383082e6f4837e` |
| current_commit | `4236edafb1f9db98143c596d23564c60392a2ded` |
| test_count / skipped_count | 188 / 1 |
| architecture_status | CLOSED |
| canonical_convergence_status | CLOSED |
| native_status | PASS |
| external_status | PASS |
| cockpit_status | PASS |
| naive_vs_governed_status | PASS |
| paper_execution_status | ENFORCED |
| proof_replay_status | PASS |
| historical_regression_status | PASS |
| known_regressions | 0 |
| canonical_contract_version | canonical.v1 |
| receipt_schema_version | receipt.v1 |
| proof_policy | PROOF_BEST_EFFORT |
| kx108_status | NO_REAL_KERNEL_CONNECTED |

## Capacite ajoutee par rapport a v0.1

Naive vs Governed Demo (`apps/naive_vs_governed/`, `apps/cockpit/naive_vs_governed_view.py`) —
promue depuis la branche `demo/naive-vs-governed-v1` (commit `2d0bb8d`), fusionnee via
`git merge --no-ff` en `4236eda`. Audit de promotion prealable : verdict **PROMOTE**,
matrice 12/12 PASS, aucune modification de fichier interdit, aucune nouvelle autorite.

## Frontiere v0.1 / v0.2

Le seal actif a la racine (`merkle_seal.json`) couvre desormais **v0.2** (87 fichiers,
`apps/` inclut maintenant la demo). Il ne prouve plus rien sur v0.1 en tant que tel.
La reference historique v0.1 (83 fichiers, root_hash
`5711dbfa0a0c4a83108eb68b66b03bb9af283240243766eb70eb67cfa06d2fd4`) reste verifiable
independamment, sans dependre de l'etat courant de l'arbre, via
`tests/unit/test_historical_seal_v0_1.py` qui relit le contenu exact du commit
`9e68391` via `git show`.

## Dettes connues

Voir `docs/FREEZE_MANIFEST_V0.2.json::known_debts` pour la liste complete et verifiee.
Toutes les dettes F10 preexistantes restent presentes et non resolues par cette
promotion (Kernel reel non branche, PAPER only, PROOF_BEST_EFFORT, Markov non
calibre, rendu Streamlit non teste, store Cockpit temporaire, packs de tests
formels du Kernel hors scope). Deux nouvelles dettes documentees : les verdicts
narratifs des scenarios B/C de la demo, et l'angle mort theorique du test AST
d'isolation du chemin Naive sur les imports dynamiques (NONE FOUND au moment du
freeze).

## Freeze v0.2

```
OBSIDIA_TRADING v0.2

ARCHITECTURE: CLOSED
CANONICAL CONVERGENCE: CLOSED
NATIVE PATH: PASS
EXTERNAL PATH: PASS
PAPER EXECUTION: PASS
PROOF / REPLAY: PASS
COCKPIT: PASS
NAIVE VS GOVERNED: PASS
HISTORICAL REGRESSION: PASS
KNOWN REGRESSIONS: 0
FREEZE: SEALED
```
