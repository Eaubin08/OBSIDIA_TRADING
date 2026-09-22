# FREEZE_MANIFEST — OBSIDIA_TRADING v0.2.1 (ACTIVE)

> Résumé lisible du manifest machine `docs/FREEZE_MANIFEST_V0.2.1.json`. En cas de
> divergence, le `.json` fait foi.

## Lignée des versions

| Version | Commit | Tag | Statut |
|---|---|---|---|
| v0.1 | `9e68391` | `obsidia-trading-v0.1-historical` | Référence historique F1→F10, intacte |
| v0.2 | `853b05e` | `obsidia-trading-v0.2-reference` | **SUPERSEDED** — voir ci-dessous |
| v0.2.1 | `391aa23` | `obsidia-trading-v0.2.1-reference` | **ACTIVE** |

Aucun tag existant n'a été déplacé ni réécrit. Chaque version reste vérifiable indépendamment.

## Pourquoi v0.2 est superseded (pas corrompue)

Le seal de v0.2 (`853b05e`) a été vérifié **interne cohérent** avant cette correction :
le root_hash recalculé indépendamment depuis le disque au HEAD de ce commit était
identique à celui documenté dans `merkle_seal.json`. **Ce n'est donc pas un défaut
d'intégrité de contenu.**

La supersession vient d'un audit de release pré-publication ayant trouvé des dettes
réelles :
1. `README.md` jamais mis à jour depuis F1 (aucune instruction d'installation, de
   lancement des tests, du Cockpit, ni mention de la démo Naive vs Governed)
2. `python-dotenv` dans `requirements.txt` sans être jamais importée
3. `.gitignore` incomplet (`.venv/`, `.idea/`, `.vscode/` absents)
4. Un champ `current_commit`/`git_commit` ambigu dans le seal et les manifests
   (capturait le HEAD au moment du calcul, pas nécessairement le HEAD courant du
   dépôt — pas un hash de contenu erroné, un problème de nommage)

## Ce que v0.2.1 corrige

Voir `release_hygiene_fixes` dans le `.json`. **Aucune capacité nouvelle, aucun
changement d'architecture, aucun changement du nombre de tests** (188 passed / 1
skipped, identique à v0.2).

| Champ | Valeur |
|---|---|
| reference_version | v0.2.1 |
| parent_reference | v0.2 (commit `853b05e`) |
| reference_tag | `obsidia-trading-v0.2.1-reference` |
| test_count / skipped_count | 188 / 1 |
| architecture_status | CLOSED |
| canonical_convergence_status | CLOSED |
| native_status / external_status | PASS / PASS |
| cockpit_status / naive_vs_governed_status | PASS / PASS |
| paper_execution_status | ENFORCED |
| proof_replay_status | PASS |
| historical_regression_status | PASS |
| known_regressions | 0 |
| proof_policy | PROOF_BEST_EFFORT |
| kx108_status | NO_REAL_KERNEL_CONNECTED |

## Dettes connues (non cachées)

Identiques à v0.2 — voir `docs/FREEZE_MANIFEST.md` section "Dettes connues" ou le
champ `known_debts` du `.json`. Aucune dette de v0.2 n'a été résolue par cette
version ; seules les dettes de *release* (ci-dessus) l'ont été.

Voir `docs/F10_HISTORICAL_REGRESSION_MATRIX.md`, `docs/SEAL_SCOPE.md`, et
`docs/history/` pour les références v0.1/v0.2 intactes.
