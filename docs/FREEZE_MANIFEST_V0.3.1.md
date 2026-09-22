# FREEZE_MANIFEST_V0.3.1 — OBSIDIA_TRADING (SUPERSEDED)

> **SUPERSEDED par v0.3.2** — raison : hygiène de métadonnées uniquement (`reference_tag` périmé dans `scripts/compute_seal.py`/`merkle_seal.json`, pointait encore vers `obsidia-trading-v0.3-reference` au lieu de `obsidia-trading-v0.3.1-reference`). Aucun changement fonctionnel, aucun défaut de contenu du seal — le `root_hash`/`sealed_file_count` de v0.3.1 étaient et restent corrects. Voir `docs/FREEZE_MANIFEST_V0.3.2.md`.
>
> Copie versionnée archivée du manifest actif au moment de v0.3.1. `docs/FREEZE_MANIFEST.md` (racine) reflète toujours la version active courante ; ce fichier reste la référence figée pour v0.3.1 spécifiquement.

## Pourquoi v0.3.1 existe

v0.3 (commit `07505c3`, tag `obsidia-trading-v0.3-reference`) est marqué **SUPERSEDED**, pas corrompu. Son manifest scellé (`docs/FREEZE_MANIFEST.md` à ce moment-là) embarquait une copie littérale du `root_hash` — mais ce document fait lui-même partie du périmètre scellé, donc le recalculer après l'avoir écrit change le contenu du fichier, et donc le root_hash réel, rendant la copie immédiatement périmée (boucle auto-référente). Conséquence observée : `expected_root_hash` et `test_count` dans `docs/FREEZE_MANIFEST_V0.3.json` ne correspondaient plus au seal réel.

**Ce qui n'était PAS affecté** : le `merkle_seal.json` réel de v0.3 restait cohérent avec le contenu effectif des fichiers scellés à ce commit (recalcul indépendant confirmé identique). Aucune corruption, aucune régression fonctionnelle — uniquement des métadonnées de référence périmées.

v0.3.1 corrige cette classe de bug : plus aucun manifest scellé ne recopie un `root_hash` littéral. `docs/FREEZE_MANIFEST.md` renvoie désormais vers `merkle_seal.json` à la racine comme seule source active.

## Lignée

| Version | Commit / parent | Tag | Statut |
|---|---|---|---|
| v0.1 | `9e68391` | `obsidia-trading-v0.1-historical` | HISTORICAL |
| v0.2 | `853b05e` | `obsidia-trading-v0.2-reference` | SUPERSEDED |
| v0.2.1 | `0c2d4f3` | `obsidia-trading-v0.2.1-reference` | SUPERSEDED |
| v0.2.2 | `557837c` | `obsidia-trading-v0.2.2-reference` | SUPERSEDED |
| v0.2.3 | `c66b379` | `obsidia-trading-v0.2.3-reference` | SUPERSEDED |
| v0.2.4 | `6864d38` | `obsidia-trading-v0.2.4-reference` | SUPERSEDED — seal cross-platform, aucun défaut fonctionnel |
| v0.3 | `07505c3` | `obsidia-trading-v0.3-reference` | SUPERSEDED — incohérence de métadonnées uniquement, seal réel non corrompu |
| v0.3.1 | parent `07505c3` | `obsidia-trading-v0.3.1-reference` | **ACTIVE** |

Aucun tag historique déplacé.

## Contenu fonctionnel (hérité de v0.3, inchangé)

- **F11 — PROOF_REQUIRED**, **F12 — Real KX108 Integration**, **F12.1 — Reference Runtime Closure**, **F13 — Real Trading Calibration**, **F13.1 — Calibration Consumption Closure**. Voir `docs/FREEZE_MANIFEST.md` (racine) pour le détail complet — identique à la section correspondante de ce fichier.

## Validation

`test_count` (tests **passés**) = **284**, `skipped_count` = **1**, `failed_count` = **0**, `total_collected` = **285**. Seal recalculé une seule fois via `scripts/compute_seal.py` après finalisation de tout contenu scellé — root actif : voir `merkle_seal.json` à la racine.

`KERNEL FILES MODIFIED = 0`, `SECRETS_COMMITTED = 0`, `SECRETS_LOGGED = 0`.

PAPER ONLY. Pas de trading live. v0.3.1 n'est pas une release live.
