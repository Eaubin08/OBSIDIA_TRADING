# Freeze Manifest — OBSIDIA_TRADING v0.2 (ACTIVE)

Résumé lisible du manifest machine `docs/FREEZE_MANIFEST.json`. En cas de divergence, le `.json` fait foi.

> **v0.1 (premier freeze, commit `e6ae249`/`9e68391`) reste une référence historique
> intacte**, archivée sous `docs/history/` et vérifiable indépendamment via
> `tests/unit/test_historical_seal_v0_1.py`. Ce document décrit désormais la version
> **active v0.2**. Voir aussi `docs/FREEZE_MANIFEST_V0.2.md` pour le schéma détaillé
> de promotion (parent_reference, added_capability, etc.).

| Champ | Valeur |
|---|---|
| project | OBSIDIA_TRADING |
| freeze_version | v0.2 |
| parent_reference | v0.1 (commit `9e68391`) |
| git_commit | `4236edafb1f9db98143c596d23564c60392a2ded` |
| test_count | 188 |
| skipped_count | 1 |
| architecture_status | CLOSED (F1→F8.7) |
| native_path_status | PASS (F8.5, F9) |
| external_path_status | PASS (F8.6, F9) |
| canonical_contract_version | canonical.v1 |
| receipt_schema_version | receipt.v1 |
| proof_policy | PROOF_BEST_EFFORT |
| paper_only_status | ENFORCED |
| kx108_status | NO_REAL_KERNEL_CONNECTED |

## Capacité ajoutée depuis v0.1

Naive vs Governed Demo, promue depuis `demo/naive-vs-governed-v1` (commit `2d0bb8d`)
via `git merge --no-ff` (`4236eda`). Audit de promotion préalable : **PROMOTE**,
12/12 critères PASS, aucune modification de fichier interdit, aucune nouvelle autorité.

## Dettes connues (non cachées)

1. Aucun vrai Kernel X-108 branché — `FixtureKX108Client` reste TEST-ONLY, comportement de production = `UnavailableKX108Client`, fail-closed.
2. Alpaca live structurellement interdit.
3. Proof policy actuelle = PROOF_BEST_EFFORT, pas PROOF_REQUIRED.
4. Matrice de régimes de Markov non calibrée sur données réelles (héritage assumé de TradingWorld).
5. Rendu Streamlit du Cockpit non testé automatiquement (seule la couche données l'est).
6. Store de receipts du Cockpit temporaire par session.
7. Packs de tests formels du Kernel (MVP-obsidia-) non portables — testent le Kernel réel, hors périmètre.
8. Les verdicts TEST FIXTURE KX108 des scénarios B/C de la démo sont des configurations narratives fixées à l'avance — juxtaposition pédagogique, pas une causalité calculée par un Kernel réel.
9. Le test AST d'isolation du chemin Naive ne couvre théoriquement pas les imports dynamiques (NONE FOUND au moment de ce freeze).

## Frontières connues

- Le score structurel local reste un **signal de domaine local**, jamais une autorité KX108 (`docs/B15_STRUCTURAL_SCORE_BOUNDARY.md`).
- Ce freeze ne prouve rien sur le Kernel X-108 de production, ni sur aucune source historique externe.
- Aucun remote git configuré, aucun push effectué à aucune étape F1→v0.2.
- **v0.1 et v0.2 ne doivent jamais être confondus** : le seal actif à la racine (`merkle_seal.json`) couvre désormais v0.2 (87 fichiers), pas v0.1 (83 fichiers, archivé séparément).

Voir `docs/F10_HISTORICAL_REGRESSION_MATRIX.md` pour l'audit de non-régression F10.1, `docs/SEAL_SCOPE.md` pour le périmètre du seal, et `docs/history/` pour la référence v0.1 intacte.
