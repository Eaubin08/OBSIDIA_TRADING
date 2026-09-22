# Freeze Manifest — OBSIDIA_TRADING v0.2.3 (ACTIVE)

Résumé lisible du manifest machine `docs/FREEZE_MANIFEST.json`. En cas de divergence, le `.json` fait foi.

> **Lignée des versions** :
> - `v0.1` (commit `9e68391`, tag `obsidia-trading-v0.1-historical`) — F1→F10, référence historique intacte.
> - `v0.2` (commit `853b05e`, tag `obsidia-trading-v0.2-reference`) — première promotion de la démo Naive vs Governed. **SUPERSEDED.** Son seal était interne cohérent (vérifié indépendamment) ; la supersession vient de dettes de release identifiées ensuite (README jamais mis à jour, dépendance inutilisée, `.gitignore` incomplet, sémantique de commit ambiguë) — pas d'une corruption de contenu.
> - `v0.2.1` (tag `obsidia-trading-v0.2.1-reference`) — corrige ces dettes de release. **SUPERSEDED.** Son seal était également interne cohérent ; la supersession vient d'un résidu purement textuel : `README.md` (dans le périmètre scellé) mentionnait encore "v0.2" au lieu de "v0.2.1" à deux endroits, laissé par inadvertance.
> - `v0.2.2` (tag `obsidia-trading-v0.2.2-reference`) — référence privée reproductible validée par clone vierge. **SUPERSEDED** par v0.2.3 uniquement pour stabiliser les pointeurs de documentation et refléter la publication distante.
> - `v0.2.3` (ce document, tag `obsidia-trading-v0.2.3-reference`) — correctif documentaire/release uniquement. **Version active.**
>
> Aucun tag existant n'a été déplacé ni réécrit ; chaque version reste vérifiable indépendamment via son propre tag.

| Champ | Valeur |
|---|---|
| project | OBSIDIA_TRADING |
| freeze_version | v0.2.3 |
| parent_reference | v0.2.2 (commit `557837c`, tag `obsidia-trading-v0.2.2-reference`) |
| reference_tag | `obsidia-trading-v0.2.3-reference` |
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

## Capacité ajoutée

Naive vs Governed Demo, promue en v0.2 depuis `demo/naive-vs-governed-v1` (commit `2d0bb8d`)
via `git merge --no-ff` (`4236eda`). Audit de promotion préalable : **PROMOTE**,
12/12 critères PASS, aucune modification de fichier interdit, aucune nouvelle autorité.
**v0.2.3 n'ajoute aucune capacité** — uniquement un correctif documentaire/release :
le README utilise désormais le pointeur stable `docs/FREEZE_MANIFEST.md` au lieu de
liens actifs versionnés susceptibles de devenir obsolètes, et le manifest actif reflète
la publication privée ainsi que la validation par clone vierge de v0.2.2.

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
- Remote GitHub privé configuré : `Eaubin08/OBSIDIA_TRADING`. La v0.2.2 a été poussée puis validée depuis un clone vierge indépendant : master/tags identiques, seal 87 fichiers MATCH, Cockpit HTTP 200, aucune dépendance locale manquante.
- **v0.1, v0.2, v0.2.1, v0.2.2 et v0.2.3 ne doivent jamais être confondus** : le seal actif à la racine (`merkle_seal.json`) couvre désormais v0.2.3 (87 fichiers), pas les versions précédentes (tagées séparément, jamais réécrites).

Voir `docs/F10_HISTORICAL_REGRESSION_MATRIX.md` pour l'audit de non-régression F10.1, `docs/SEAL_SCOPE.md` pour le périmètre du seal, et `docs/history/` pour la référence v0.1 intacte.


## Validation distante

- Dépôt : `Eaubin08/OBSIDIA_TRADING` (PRIVATE)
- Baseline transport validée : v0.2.2, clone vierge indépendant
- Résultat : `PRIVATE_REMOTE_REPRODUCIBLE`
- Suite baseline : 188 passed / 1 skipped / 0 failed
- v0.2.3 ne modifie aucun fichier de code de production ni de test.
