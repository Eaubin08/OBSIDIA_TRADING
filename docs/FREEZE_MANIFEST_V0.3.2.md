# FREEZE_MANIFEST_V0.3.2 — OBSIDIA_TRADING (ACTIVE)

> Copie versionnée archivée du manifest actif. `docs/FREEZE_MANIFEST.md` (racine) reflète toujours la version active courante ; ce fichier reste la référence figée pour v0.3.2 spécifiquement.

## Pourquoi v0.3.2 existe

v0.3.1 (commit `2661332`, tag `obsidia-trading-v0.3.1-reference`) est marqué **SUPERSEDED**, pas corrompu. `scripts/compute_seal.py` et `merkle_seal.json` contenaient encore `"reference_tag": "obsidia-trading-v0.3-reference"` — une métadonnée périmée d'une version à l'autre (elle aurait dû être mise à jour vers `v0.3.1` lors du freeze précédent, ce qui n'a pas été fait). Aucun impact sur le contenu réel du seal : `root_hash` et `sealed_file_count` de v0.3.1 étaient et restent corrects.

v0.3.2 corrige uniquement cette référence, dans `scripts/compute_seal.py`, pour qu'elle porte désormais et à l'avenir le bon `reference_tag`.

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
| v0.3.1 | `2661332` | `obsidia-trading-v0.3.1-reference` | SUPERSEDED — `reference_tag` périmé uniquement, seal réel non corrompu |
| v0.3.2 | parent `2661332` | `obsidia-trading-v0.3.2-reference` | **ACTIVE** |

Aucun tag historique déplacé.

## Contenu fonctionnel (hérité de v0.3/v0.3.1, inchangé)

- **F11 — PROOF_REQUIRED**, **F12 — Real KX108 Integration**, **F12.1 — Reference Runtime Closure**, **F13 — Real Trading Calibration**, **F13.1 — Calibration Consumption Closure**. Voir `docs/FREEZE_MANIFEST.md` (racine) pour le détail complet.

## Validation

`test_count` (tests **passés**) = **284**, `skipped_count` = **1**, `failed_count` = **0**, `total_collected` = **285** — inchangé par rapport à v0.3.1, aucun test ajouté/retiré/modifié. Seal recalculé une seule fois via `scripts/compute_seal.py` après finalisation de tout contenu scellé — root actif : voir `merkle_seal.json` à la racine.

`KERNEL FILES MODIFIED = 0`, `SECRETS_COMMITTED = 0`, `SECRETS_LOGGED = 0`.

PAPER ONLY. Pas de trading live. v0.3.2 n'est pas une release live.
