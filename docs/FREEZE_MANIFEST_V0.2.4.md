# FREEZE_MANIFEST — OBSIDIA_TRADING v0.2.4 (SUPERSEDED)

> **SUPERSEDED par v0.3** : aucun défaut fonctionnel ici. v0.3 promeut F11 (PROOF_REQUIRED) → F12 (Real KX108 Integration) → F12.1 (Reference Runtime Closure) → F13 (Real Trading Calibration) → F13.1 (Calibration Consumption Closure) vers master. v0.2.4 reste une référence historique intacte et indépendamment vérifiable.

v0.2.4 est une correction du mécanisme de release/seal uniquement. Aucun mécanisme métier, aucune autorité, aucun Binder, aucun chemin d'exécution et aucun test fonctionnel ne change.

## Pourquoi v0.2.4 existe

Après v0.2.3, la suite locale a donné **188 passed, 1 skipped, 0 failed**, mais a aussi montré qu'un même contenu Git pouvait produire un root différent selon les fins de ligne du working tree (CRLF sous Windows, LF côté GitHub/Linux).

La cause était `file_hash(path) = sha256(path.read_bytes())` : le seal dépendait donc de la représentation locale des fins de ligne.

## Correction

À partir de v0.2.4 :

- les fichiers texte scellés sont normalisés `CRLF -> LF` puis `CR -> LF` avant SHA-256 ;
- `.gitattributes` force LF pour les futurs checkouts ;
- `docs/SEAL_SCOPE.md` documente cette canonicalisation ;
- le même commit doit produire le même root sur Windows, Linux et GitHub.

## Statut

- Tests baseline : **188 passed / 1 skipped / 0 failed**
- Sealed files : **87**
- Expected root : `c1a4b81c61a13da077dd8d78b6c8a2698b6c670be7165baddba0c91848d86cb2`
- Architecture : CLOSED
- Native / External : PASS / PASS
- PAPER ONLY : ENFORCED
- Kernel réel : NON CONNECTÉ
- Remote : PRIVATE
- Capability change : NONE

Les tags v0.1 à v0.2.3 restent historiques et ne doivent pas être déplacés.
