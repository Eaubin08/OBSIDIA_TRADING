# FREEZE_MANIFEST — OBSIDIA_TRADING v0.3 (ACTIVE)

> Résumé lisible du manifest machine `docs/FREEZE_MANIFEST_V0.3.json`. En cas de divergence, le `.json` fait foi.

## Lignée

| Version | Commit / parent | Tag | Statut |
|---|---|---|---|
| v0.1 | `9e68391` | `obsidia-trading-v0.1-historical` | HISTORICAL |
| v0.2 | `853b05e` | `obsidia-trading-v0.2-reference` | SUPERSEDED |
| v0.2.1 | `0c2d4f3` | `obsidia-trading-v0.2.1-reference` | SUPERSEDED |
| v0.2.2 | `557837c` | `obsidia-trading-v0.2.2-reference` | SUPERSEDED |
| v0.2.3 | `c66b379` | `obsidia-trading-v0.2.3-reference` | SUPERSEDED |
| v0.2.4 | `6864d38` | `obsidia-trading-v0.2.4-reference` | SUPERSEDED — seal cross-platform, aucun défaut fonctionnel |
| v0.3 | parent `6864d38` | `obsidia-trading-v0.3-reference` | **ACTIVE** |

Aucun tag historique n'a été déplacé.

## Ce que v0.3 promeut

Fusion (`merge --no-ff`, généalogie complète préservée) de la chaîne F11→F13.1, entièrement auditée et ré-exécutée avant promotion :

- **F11 — PROOF_REQUIRED** : deux politiques de preuve coexistent explicitement (`BEST_EFFORT` héritée, `REQUIRED` pour le chemin critique). Sous `REQUIRED`, une preuve injoignable bloque l'exécution *avant* tout appel broker. Un succès broker suivi d'un échec de persistance finale n'est jamais présenté comme un succès ou un échec — `ProofOutcome.EXECUTION_SUCCEEDED_PROOF_INCOMPLETE` préserve l'incertitude réelle. La chaîne de receipts n'avance jamais sur un receipt jamais persisté.
- **F12 — Real KX108 Integration** : `RealKX108Client` joint réellement le Kernel X-108 scellé du core (`server.kernel.sealed.cjs`, `POST /kernel/ragnarok`, port 3001), jamais modifié. Round-trip réel confirmé pour les chemins Native et External. Écart de contrat découvert et documenté (`x108_gate` vs `verdict` attendu par le gate historique du core) — normalisé côté Trading uniquement, jamais corrigé dans le core.
- **F12.1 — Reference Runtime Closure** : garde-fou par construction — `CycleEngine` refuse de combiner `RealKX108Client` avec `ProofPolicy.BEST_EFFORT` (`RealKernelRequiresProofRequired`). Le runtime de référence gouverné critique est donc verrouillé sur `REQUIRED` dès qu'un vrai Kernel est branché.
- **F13 — Real Trading Calibration** : `CalibrationPack` construit à partir de vraies données de marché Alpaca paper (AAPL, 171 barres quotidiennes), avec split train/évaluation disjoint. `realized_volatility`, `garch_1_1` (grid-search) et `markov_regime_matrix` (comptage réel des transitions) tous `CALIBRATED`.
- **F13.1 — Calibration Consumption Closure** : `VolatilityAgent` et `RegimeShiftAgent` consomment réellement la calibration (fallback/evidence, jamais le verdict de l'agent recalculé). Les 15 autres agents refusent honnêtement (`NO_RELEVANT_REAL_DATA`/`N/A`). Symbol mismatch, calibration périmée ou absente → refus/`unknown` explicite. Chemin External confirmé indépendant du `CalibrationPack` Native.

## Statut technique

- Architecture : CLOSED
- Canonical convergence : CLOSED
- Native / External : PASS / PASS
- Cockpit / Naive vs Governed : PASS / PASS
- PAPER execution : ENFORCED — LIVE trading FORBIDDEN
- Proof / Replay : PASS
- Proof policy : `BEST_EFFORT` par défaut (rétrocompatible) ; `REQUIRED` **appliqué par construction** pour tout runtime combinant Real Kernel
- KX108 : Kernel réel intégré et prouvé (round-trip PASS), **mais pas activé par défaut** — la production par défaut de ce repo reste `UnavailableKX108Client` (fail-closed)
- Calibration : RÉELLE (données Alpaca paper, AAPL), consommation fermée pour les 2 agents pertinents
- Historical regression : PASS
- Known regressions : 0

## Validation

`pytest tests/ -q` sur `master` post-merge : **283 passed / 1 skipped / 0 failed**. Seal v0.3 recalculé via `scripts/compute_seal.py` (mécanisme cross-platform introduit en v0.2.4, jamais calculé à la main) : **93 fichiers scellés**, root_hash `b0f6b167793117df3436ad665ff2712f799e24c243b57cf25f6a520cfe282d02` — `tests/unit/test_freeze_manifest.py` **vert**.

Kernel boundary : `KERNEL FILES MODIFIED = 0`, `KERNEL COMMITS CREATED = 0`, `KERNEL TAGS MOVED = 0` (vérifié avant et après chaque round-trip réel).

Secrets : `SECRETS_COMMITTED = 0`, `SECRETS_LOGGED = 0` (grep exhaustif sur tout l'historique git).

Remote : `Eaubin08/OBSIDIA_TRADING` — **PRIVATE**. Reproductibilité clone-vierge validée jusqu'à v0.2.2 ; non re-testée explicitement pour le contenu v0.3 dans cette session (dette documentée).

## Dettes connues (non masquées)

- Calibration mono-symbole (AAPL), mono-fenêtre (171 barres).
- GARCH(1,1) par grid-search simple, pas une MLE complète.
- 15/17 agents non calibrés faute de données Macro/Event/Sentiment/cross-asset réelles.
- `ProofPolicy.BEST_EFFORT` reste le défaut hors chemin Real Kernel.
- Rendu Streamlit du Cockpit non testé automatiquement.
- Store de receipts du Cockpit temporaire par session.
- Packs de tests formels du Kernel `NOT_PORTABLE`.
- Verdicts fixture des scénarios B/C de la démo Naive vs Governed = configurations narratives, pas une causalité calculée.
- Angle mort théorique du test AST d'isolation Naive sur les imports dynamiques (aucun trouvé, non corrigé par un système dédié).
- v0.3 non revalidée depuis un clone GitHub vierge indépendant dans cette session.

PAPER ONLY. Pas de trading live. v0.3 n'est pas une release live.
