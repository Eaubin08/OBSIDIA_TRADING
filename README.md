# OBSIDIA_TRADING

Implémentation de référence active du domaine Trading gouverné par Obsidia.

## What is OBSIDIA_TRADING?

```
Market
  ↓
Trading cognition (agents natifs OU stack externe via adapter)
  ↓
Canonical Domain Contract
  ↓
Simulation / Evidence
  ↓
TradeIntent
  ↓
Governance Bridge (Sigma / Guard)
  ↓
KX108 (seule autorité de décision : ACT / HOLD / BLOCK)
  ↓
Binder (vérifie le verdict, ne le fabrique jamais)
  ↓
PAPER Execution (broker adapter)
  ↓
Receipt (preuve chaînée, ne décide jamais)
  ↓
Proof / Replay
```

Chaque flèche est une frontière de responsabilité, pas une simple étape : un agent ne devient jamais une autorité, une simulation ne devient jamais une décision, un receipt ne devient jamais lui-même la décision qu'il enregistre.

## Native vs External — le Canonical Convergence Point

### Native Reference Implementation (`native/`)
Obsidia fournit le domaine Trading complet : agents (17), stratégies, indicateurs, portfolio, risk, calibration. C'est le laboratoire métier et la vitrine montrable à une entreprise.

### External Stack Adapter (`external/`)
Une entreprise (ou une stack tierce) garde ses propres agents/règles/données et les branche à la même gouvernance via un adapter de normalisation.

**Les deux chemins convergent avant l'autorité**, au niveau de `domain/contracts/canonical.py` (`to_canonical_agent_signal` — un seul builder, utilisé par les deux chemins). Après ce point, la provenance Native/External ne change jamais le comportement de la gouvernance. Il n'y a jamais deux kernels.

## Current status — Active Reference Implementation

```
283 passed
1 skipped
0 known regression
PAPER ONLY
```

Voir `docs/FREEZE_MANIFEST.md` pour le manifest actif, et `merkle_seal.json` (+ `docs/SEAL_SCOPE.md`) pour le périmètre scellé. La v0.1 (F1→F10, avant la démo Naive vs Governed) reste une référence historique intacte et indépendamment vérifiable sous `docs/history/` — voir `docs/DEMO_BRANCH_SEAL_STATUS.md` pour le détail de la promotion.

## Critical boundaries

- **Aucun vrai Kernel X-108 n'est connecté dans ce repo.** Tout ce qui ressemble à un verdict KX108 ici provient d'un `FixtureKX108Client` explicitement **TEST-ONLY** (`tests/test_support/`) — le comportement de production par défaut est `UnavailableKX108Client`, **fail-closed** (`HOLD` sur indisponibilité ou réponse invalide, jamais `ACT` par défaut).
- **LIVE trading est structurellement interdit.** `require_paper_mode()` refuse toute tentative de passage en mode live avant même la construction d'un client réseau.
- **Simulation ≠ Authority.** Une simulation produit une preuve/evidence, jamais un verdict.
- **Receipt ≠ Decision.** Persister un receipt ne peut jamais changer rétroactivement la décision qu'il documente.
- **Replay ≠ Execution.** Un replay (audit ou déterministe) ne déclenche jamais d'appel broker.

Voir `docs/B15_STRUCTURAL_SCORE_BOUNDARY.md` pour la limite spécifique sur la formule de score structurel local (signal, jamais autorité — non vérifiable contre le vrai Kernel depuis ce repo).

## Installation

```bash
pip install -r requirements.txt
```

## Tests

```bash
pytest tests/ -q
```

Attendu : `188 passed, 1 skipped`.

## Cockpit

```bash
streamlit run apps/cockpit/app.py
```

Le Cockpit est une **projection observable** du runtime réel (CycleEngine, GovernanceBridge, ReceiptStore, ReplayEngine) — il ne recalcule jamais un verdict lui-même. Il affiche notamment un sélecteur pour la vue "Naive vs Governed".

## Naive vs Governed

Démonstration pédagogique intégrée au Cockpit (`apps/naive_vs_governed/`) : à partir des mêmes entrées, compare un chemin **Naive** (contrefactuel, isolé, sans aucun accès Broker/Binder/Governance/KX108) et le chemin **Governed** réel (réutilise strictement le runtime déjà prouvé — CycleEngine, GovernanceBridge, Binder, ReceiptStore).

- Le chemin Naive est **counterfactual/demo only** — il n'importe jamais `governance`, `execution.binder`, ni `market.adapters.alpaca`, prouvé par test structurel (`tests/unit/test_naive_vs_governed.py`).
- Les verdicts affichés proviennent toujours du `FixtureKX108Client` — **TEST FIXTURE, jamais un vrai Kernel**. Pour les scénarios B/C, le verdict est une configuration narrative fixée à l'avance (le fixture ne dérive aucun verdict à partir des unknowns/contradictions observés) ; le texte affiché juxtapose les faits sans affirmer de lien causal calculé.
- La démo ne prétend **jamais** que le chemin gouverné est plus rentable ou produit de meilleures prédictions — elle porte sur la gouvernance elle-même (unknowns, contradictions, risk flags, permission, sécurité d'exécution, preuve, replay), pas sur la performance financière.

## Repository structure

| Dossier | Contenu |
|---|---|
| `domain/` | Types canoniques, contrats, provenance, état de marché/portfolio |
| `native/` | Roster d'agents natifs (17) et leur adaptation vers le contrat canonique |
| `external/` | Adapter générique pour stacks Trading externes |
| `market/` | Adapters de marché (Alpaca paper) |
| `simulation/` | Monte Carlo, moteur de marché (GBM/Markov/GARCH/jumps), métriques de risque |
| `governance/` | Governance Bridge vers KX108 |
| `execution/` | Binder, moteur de cycle, exécution paper |
| `proof/` | Receipts chaînés, persistance, vérification d'intégrité, replay |
| `apps/` | Cockpit (Streamlit) et démo Naive vs Governed |
| `docs/` | Manifests de freeze, provenance de migration, limites connues |

## Known limitations

Voir `docs/FREEZE_MANIFEST.md` (section `Dettes connues`) pour la liste exacte et à jour. Résumé :
- Aucun vrai Kernel X-108 branché (fail-closed par construction)
- Politique de preuve actuelle = `PROOF_BEST_EFFORT` (pas `PROOF_REQUIRED`)
- Matrice de régimes de Markov **non calibrée** sur données réelles
- Rendu visuel Streamlit non testé automatiquement (seule la couche données l'est)
- Store de receipts du Cockpit temporaire par session
- Verdicts fixture des scénarios B/C de la démo = configurations narratives, pas une dérivation causale réelle

Aucune de ces limites n'est cachée : chacune est documentée dans le code et/ou les manifests, jamais seulement par omission.
