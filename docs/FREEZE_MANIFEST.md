# Freeze Manifest — OBSIDIA_TRADING v0.1

Résumé lisible du manifest machine `docs/FREEZE_MANIFEST.json`. En cas de divergence, le `.json` fait foi.

| Champ | Valeur |
|---|---|
| project | OBSIDIA_TRADING |
| freeze_version | v0.1 (premier freeze) |
| git_commit | voir `docs/FREEZE_MANIFEST.json` (rempli après commit du freeze) |
| test_count | 168 |
| skipped_count | 1 |
| architecture_status | CLOSED (F1→F8.7) |
| native_path_status | PASS (F8.5, F9) |
| external_path_status | PASS (F8.6, F9) |
| canonical_contract_version | canonical.v1 (première version, `domain/contracts/canonical.py`) |
| receipt_schema_version | receipt.v1 (`domain/receipt.py::RECEIPT_SCHEMA_VERSION`) |
| proof_policy | PROOF_BEST_EFFORT (un échec d'écriture du receipt est journalisé, n'interrompt pas le cycle) |
| paper_only_status | ENFORCED (`require_paper_mode`, aucune clé live) |
| kx108_status | NO_REAL_KERNEL_CONNECTED (fail-closed par défaut) |

## Dettes connues (non cachées)

1. Aucun vrai Kernel X-108 branché — `FixtureKX108Client` reste TEST-ONLY, comportement de production = `UnavailableKX108Client`, fail-closed.
2. Alpaca live structurellement interdit.
3. Proof policy actuelle = PROOF_BEST_EFFORT, pas PROOF_REQUIRED.
4. Matrice de régimes de Markov non calibrée sur données réelles (héritage assumé de TradingWorld).
5. Rendu Streamlit du Cockpit non testé automatiquement (seule la couche données l'est).
6. Store de receipts du Cockpit temporaire par session.
7. "Naive vs Governed" (MVP-obsidia-) jamais implémenté — `apps/naive_vs_governed/` vide.
8. Packs de tests formels du Kernel (MVP-obsidia-) non portables — testent le Kernel réel, hors périmètre.

## Frontières connues

- Le score structurel local reste un **signal de domaine local**, jamais une autorité KX108 (`docs/B15_STRUCTURAL_SCORE_BOUNDARY.md`).
- Ce freeze ne prouve rien sur le Kernel X-108 de production, ni sur aucune source historique externe.
- Aucun remote git configuré, aucun push effectué à aucune étape F1→F10.

Voir `docs/F10_HISTORICAL_REGRESSION_MATRIX.md` pour l'audit complet de non-régression, et `docs/SEAL_SCOPE.md` pour le périmètre exact du `merkle_seal.json` dédié à ce repo.
