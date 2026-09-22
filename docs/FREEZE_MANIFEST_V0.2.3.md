# FREEZE_MANIFEST — OBSIDIA_TRADING v0.2.3 (SUPERSEDED)

> Résumé lisible du manifest machine `docs/FREEZE_MANIFEST_V0.2.3.json`. En cas de divergence, le `.json` fait foi.

## Lignée

| Version | Commit / parent | Tag | Statut |
|---|---|---|---|
| v0.1 | `9e68391` | `obsidia-trading-v0.1-historical` | HISTORICAL |
| v0.2 | `853b05e` | `obsidia-trading-v0.2-reference` | SUPERSEDED |
| v0.2.1 | `0c2d4f3` | `obsidia-trading-v0.2.1-reference` | SUPERSEDED |
| v0.2.2 | `557837c` | `obsidia-trading-v0.2.2-reference` | SUPERSEDED — intègre, PRIVATE_REMOTE_REPRODUCIBLE |
| v0.2.3 | parent `557837c` | `obsidia-trading-v0.2.3-reference` | **ACTIVE** |

Aucun tag historique ne doit être déplacé.

## Objet de v0.2.3

Aucune capacité nouvelle et aucun changement d'architecture. Cette version ferme uniquement deux résidus de release :

1. le README ne code plus en dur un lien de manifest actif versionné ; il pointe vers `docs/FREEZE_MANIFEST.md`, qui est le pointeur actif stable ;
2. le manifest actif reflète maintenant la réalité distante : dépôt GitHub privé configuré et v0.2.2 validée depuis un clone vierge indépendant.

## Statut technique

- Architecture : CLOSED
- Canonical convergence : CLOSED
- Native / External : PASS / PASS
- PAPER execution : ENFORCED
- Proof / Replay : PASS
- Historical regression : PASS
- Known regressions : 0
- Kernel réel : NON CONNECTÉ dans ce repo
- Proof policy : PROOF_BEST_EFFORT

## Validation

Baseline fonctionnelle inchangée : **188 passed / 1 skipped / 0 failed** sur le clone vierge v0.2.2. v0.2.3 ne modifie aucun fichier de code de production ni de test.

Remote : `Eaubin08/OBSIDIA_TRADING` — **PRIVATE**.

Transport baseline : **PRIVATE_REMOTE_REPRODUCIBLE**.

Le seal actif couvre 87 fichiers selon `docs/SEAL_SCOPE.md`.


> **SUPERSEDED par v0.2.4** : aucun défaut fonctionnel. La validation locale `188 passed / 1 skipped / 0 failed` a révélé que le mécanisme de seal v0.2.3 dépendait des fins de ligne du working tree (CRLF Windows vs LF GitHub/Linux). v0.2.4 normalise désormais les fins de ligne avant hash.
