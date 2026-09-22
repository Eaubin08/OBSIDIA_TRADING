# DEMO_BRANCH_SEAL_STATUS — demo/naive-vs-governed-v1

## Statut : EXPECTED_POST_FREEZE_SCOPE_CHANGE

`master` reste gelé au commit `9e68391` (F10 v0.1). Cette branche ajoute des fichiers sous
`apps/` (démo Naive vs Governed) postérieurs à ce freeze.

Le test `tests/unit/test_freeze_manifest.py::test_merkle_seal_exists_and_root_hash_is_recomputable`
échoue **volontairement et correctement** sur cette branche : il attend 83 fichiers scellés
(périmètre `apps/**/*.py` au moment du freeze F10) et en trouve 87 (nouveaux fichiers démo
inclus dans ce même pattern glob).

**Ce n'est pas une altération du seal.** `merkle_seal.json`, `docs/FREEZE_MANIFEST.{json,md}`
et `docs/SEAL_SCOPE.md` sont strictement identiques à leur état sur `master` (vérifié par diff).
Le test échoue parce qu'il fait exactement ce pour quoi il a été conçu : détecter qu'un état
post-freeze n'est plus identique à la Reference Implementation scellée.

## Ce que ce résultat signifie

```
master (F10 v0.1)             → frozen reference → seal verification = PASS
demo/naive-vs-governed-v1     → post-freeze dev   → seal verification = FAIL (attendu)
```

Cette branche **n'est pas** et **ne prétend pas être** identique à F10 v0.1. C'est une propriété
souhaitée, pas un défaut à corriger.

## Ce qui n'a pas été fait, volontairement

- Le périmètre du seal (`apps/**/*.py` dans `docs/SEAL_SCOPE.md`) n'a pas été restreint pour
  faire disparaître l'échec.
- `merkle_seal.json` n'a pas été régénéré pour inclure les nouveaux fichiers.
- Le test de vérification n'a pas été modifié ou assoupli.

## Procédure de promotion future (si décidée séparément)

Si la démo est un jour fusionnée vers `master`, elle suivra une procédure séparée et explicite :
1. régression complète de la branche
2. audit du diff contre `9e68391`
3. validation explicite de la démo
4. merge/promotion contrôlée
5. nouveau freeze manifest versionné (v0.2)
6. nouveau `merkle_seal.json` couvrant le nouvel état
7. conservation du freeze F10 v0.1 comme référence historique intacte

Aucune de ces étapes n'a été engagée. Cette note documente uniquement l'état actuel.
