# FREEZE_MANIFEST — OBSIDIA_TRADING v0.2.2 (SUPERSEDED)

> Résumé lisible du manifest machine `docs/FREEZE_MANIFEST_V0.2.2.json`. En cas de
> divergence, le `.json` fait foi.

## Lignée des versions

| Version | Commit | Tag | Statut |
|---|---|---|---|
| v0.1 | `9e68391` | `obsidia-trading-v0.1-historical` | Référence historique F1→F10, intacte |
| v0.2 | `853b05e` | `obsidia-trading-v0.2-reference` | **SUPERSEDED** — audit de release |
| v0.2.1 | `391aa23` | `obsidia-trading-v0.2.1-reference` | **SUPERSEDED** — résidu README |
| v0.2.2 | `557837c` | `obsidia-trading-v0.2.2-reference` | **SUPERSEDED** — doc/release hygiene uniquement |
| v0.2.3 | voir manifest actif | `obsidia-trading-v0.2.3-reference` | **ACTIVE** |

Aucun tag existant n'a été déplacé ni réécrit. Chaque version reste vérifiable indépendamment.

> **SUPERSEDED par v0.2.3** : v0.2.2 reste intègre et a été validée depuis un clone vierge (`PRIVATE_REMOTE_REPRODUCIBLE`). La supersession est uniquement documentaire/release : pointeurs README stabilisés et état distant reflété dans le manifest actif.

## Pourquoi v0.2.1 est superseded (pas corrompue)

Le seal de v0.2.1 (`391aa23`) a été vérifié **interne cohérent**. La supersession
vient d'un résidu purement textuel : `README.md` (dans le périmètre scellé, voir
`docs/SEAL_SCOPE.md`) contenait encore les mentions de version active **"v0.2"** au
lieu de **"v0.2.1"**, à deux endroits (titre, section "Current status"). Ce résidu a
été laissé par inadvertance : le README avait été réécrit dans un commit antérieur
(`391aa23` lui-même) à la décision de nommer cette version "v0.2.1" plutôt que de
patcher v0.2 en place — le texte de version n'a simplement jamais été mis à jour pour
refléter ce nom de version final.

**Ce n'est donc ni un défaut d'intégrité, ni une erreur de contenu fonctionnel.**

## Ce que v0.2.2 corrige

1. `README.md` : les deux mentions de version active corrigées "v0.2" → "v0.2.2"
   (pas "v0.2 → v0.2.1", puisque v0.2.1 est elle-même déjà superseded). La référence
   historique légitime à "v0.1" ailleurs dans le fichier reste inchangée.
2. `README.md` : le lien vers le manifest complet pointe désormais vers
   `docs/FREEZE_MANIFEST_V0.2.2.md`.
3. `scripts/compute_seal.py` : la constante `reference_tag` pointe désormais vers
   `obsidia-trading-v0.2.2-reference`.
4. Vérification exhaustive (grep) : aucune autre mention de version active obsolète
   trouvée dans les fichiers `.py` de production du périmètre scellé, ni dans
   `docs/B15_STRUCTURAL_SCORE_BOUNDARY.md`, `docs/MIGRATION_PROVENANCE.md`,
   `docs/F10_HISTORICAL_REGRESSION_MATRIX.md`.

**Aucune capacité nouvelle, aucun changement d'architecture, aucun changement du
nombre de tests** (188 passed / 1 skipped, identique à v0.2 et v0.2.1).

| Champ | Valeur |
|---|---|
| reference_version | v0.2.2 |
| parent_reference | v0.2.1 (commit `391aa23`) |
| reference_tag | `obsidia-trading-v0.2.2-reference` |
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

Identiques à v0.2 et v0.2.1 — voir `docs/FREEZE_MANIFEST.md` section "Dettes connues"
ou le champ `known_debts` du `.json`. Aucune dette architecturale n'a été résolue par
cette version ; seul le résidu documentaire ci-dessus l'a été.

Voir `docs/F10_HISTORICAL_REGRESSION_MATRIX.md`, `docs/SEAL_SCOPE.md`, et
`docs/history/` pour les références v0.1/v0.2/v0.2.1 intactes.
