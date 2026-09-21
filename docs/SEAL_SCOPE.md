# Seal Scope — OBSIDIA_TRADING merkle_seal.json

Ce document définit exactement ce que le `merkle_seal.json` de ce repo couvre, et ce qu'il ne couvre pas. Il ne remplace ni ne modifie le `merkle_seal.json` du core Obsidia (`obsidia-x108-proofs_REMOTE_A5F21C6B`), qui reste intact et hors périmètre.

## What is sealed

Tous les fichiers `*.py` de production sous les dossiers suivants :
- `domain/` (y compris `domain/ports/`, `domain/contracts/`)
- `native/`
- `external/`
- `market/`
- `simulation/`
- `governance/`
- `execution/`
- `proof/`
- `apps/`

Plus les documents de gouvernance suivants (racine et `docs/`) :
- `README.md`
- `docs/B15_STRUCTURAL_SCORE_BOUNDARY.md`
- `docs/MIGRATION_PROVENANCE.md`
- `docs/F10_HISTORICAL_REGRESSION_MATRIX.md`
- `docs/FREEZE_MANIFEST.md`

## What is NOT sealed

- `tests/` (tout le dossier — les tests prouvent le comportement mais ne sont pas eux-mêmes le contrat scellé)
- `__pycache__/`, `*.pyc`, `.pytest_cache/`
- `.git/`
- `proof/receipts/data/` (données produites à l'exécution, jamais figées)
- `requirements.txt`, `.env.example`, `.gitignore` (configuration, pas contrat de gouvernance)
- Tout fichier hors des dossiers listés ci-dessus
- Toute source historique externe (agent-trad-main, core Obsidia, clones d'audit) — ce seal ne prouve rien à leur sujet

## Ce que ce seal PROUVE

Que le code de production listé ci-dessus, à l'instant du scellement, correspond exactement au root hash publié dans `merkle_seal.json`. Rien de plus.

## Ce que ce seal NE PROUVE PAS

- Il ne prouve rien sur le comportement du Kernel X-108 réel (externe, scellé, jamais accédé depuis ce repo).
- Il ne prouve pas que les tests passent (voir `docs/FREEZE_MANIFEST.md` pour le résultat de tests au moment du freeze, séparément).
- Il ne prouve pas l'absence de bug — seulement l'intégrité/non-altération du code listé.
- Il ne couvre aucune source historique (agent-trad-main, MVP-obsidia-, Obsidia-lab-trad, etc.) — ces sources restent hors scope, non scellées par ce document.

## Hash algorithm

SHA-256, cohérent avec le reste de l'écosystème Obsidia (`merkle_seal.json` du core).

## Mécanisme de calcul (reproductible)

1. Pour chaque fichier inclus (liste triée par chemin relatif POSIX, `/` comme séparateur), calculer `sha256(contenu_binaire_du_fichier)`.
2. Construire la liste triée des paires `(chemin_relatif, hash_fichier)`.
3. Sérialiser cette liste en JSON canonique : `json.dumps(paires, sort_keys=True, separators=(",", ":"))`.
4. `root_hash = sha256(json_canonique.encode("utf-8")).hexdigest()`.

Le script `scripts/compute_seal.py` implémente exactement cet algorithme et régénère `merkle_seal.json` de façon déterministe — deux exécutions sur le même contenu produisent le même `root_hash`.
