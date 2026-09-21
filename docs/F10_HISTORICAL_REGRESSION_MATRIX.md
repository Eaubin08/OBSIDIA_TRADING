# F10.1 — Historical Regression / Compatibility Audit

> Audit comparatif, 2026-09-21. Sources historiques en lecture seule, aucune modification.
> Sources effectivement disponibles pour relecture directe : `AGENT_TRAD_MAIN_BACKUP_20260921` (garanti), core actuel `obsidia-x108-proofs_REMOTE_A5F21C6B` (garanti), clones temporaires `MVP-obsidia-` / `Obsidia-lab-trad` / `agentic-commerce-safe-demo-V2-...` (toujours présents sous `C:\Users\User\.claude\jobs\c17af3cb\tmp\audit_clones\`), archive ERC-8004 sous `zone tampon obsidia/.../v1.5.0-STABLE/_imports_ready/trading/agent-trad/` (toujours présente). Aucune source n'a dû être reconstituée depuis les rapports d'audit seuls — toutes relues directement.

## 1. MVP-obsidia-

| Historical Property | Source | Old Implementation | Current Equivalent | Status | Evidence |
|---|---|---|---|---|---|
| Bootstrap Monte Carlo | MVP-obsidia- | `src/simulation/sim_lite.py::sim_lite_bootstrap` — rééchantillonnage sur fenêtre glissante, μ/σ/P(drawdown)/CVaR95 | `simulation/monte_carlo/bootstrap.py` (F4) | PRESERVED | Formule EXTRACT_PATTERN_ONLY, dataset factice écarté, seed optionnel ajouté (amélioration) |
| Naive vs Governed | MVP-obsidia- | `app/views/os4_reports_extended.py::render_naive_vs_governed` — comparaison statique côte-à-côte (texte descriptif, pas de calcul réel) | `apps/naive_vs_governed/` (dossier créé en F1, **vide**) | MISSING | `ls apps/naive_vs_governed/` → aucun fichier. Le concept n'a pas été porté, même si le comparateur `gap_status` (bank-robo) documenté comme pattern de remplacement en F0 n'a pas non plus été implémenté |
| Temporal HOLD | MVP-obsidia- | `src/gates/gate2_x108_temporal.py::gate2_x108_temporal` — `dt < hold_seconds` puis seuil de cohérence, logique inline sans séparation propose/décide | Double barrière `ExecutionPlanner`/`_execute` (F3/F6) + `KX108GovernanceBridge` fail-closed (F5) | REPLACED_EQUIVALENTLY | Le nouveau mécanisme sépare strictement observation (score local), décision (KX108 fixture) et permission (Binder) — le vieux gate mélangeait tout dans une fonction ; supériorité architecturale documentée en F5/F6, testée (`tests/unit/test_governance_bridge.py`, `tests/integration/test_paper_execution_pipeline.py`) |
| Proof Mode / Free Mode | MVP-obsidia- | `app/config.py::MODES = ["Proof (Deterministic)", "Free (Non-deterministic)"]` — simple flag de config, aucun mécanisme de preuve réel derrière | `proof_policy` PROOF_REQUIRED / PROOF_BEST_EFFORT documenté (F7, `docs/MIGRATION_PROVENANCE.md` §F7) + `ReceiptChainVerifier` réel | IMPROVED | Le nouveau mécanisme a une vraie chaîne de preuve vérifiable (hash-chain, F7) contre un simple label UI côté MVP |
| OS1 Observation | MVP-obsidia- | Chargement CSV statique (48 lignes synthétiques) + Plotly, zéro exécution | `market/adapters/alpaca/` (F2) — vraies données de marché via API (paper), + `domain/state.py::TradingDomainState` | IMPROVED | MVP n'avait aucune source de données réelle ; F2 a une intégration Alpaca fonctionnelle et testée |
| OS2 Simulation | MVP-obsidia- | Bootstrap Monte Carlo (voir ligne 1) | Bootstrap (F4) + moteur paramétrique GBM/Markov/GARCH/jumps (F4) | IMPROVED | Deux moteurs complémentaires contre un seul côté MVP |
| OS3 Governance | MVP-obsidia- | Formulaire d'intent + gate2 inline + émission ERC-8004 stub ("hackathon-safe" dans le code source lui-même) | `governance/bridge/` (F5) + `domain/proposal.py::AgentOutput`/`TradeIntent` | REPLACED_EQUIVALENTLY | Le TradeIntent d'agent-trad-main/F3.5 est un concept mûr, testé, non qualifié "hackathon-safe" par son propre code |
| OS4 Reports | MVP-obsidia- | Onglets Artifacts/Human Algebra/Proofs/Naive vs Governed/Timeline (UI Streamlit statique) | `apps/cockpit/` (F9) — 11 sections dynamiques lisant le runtime réel | REPLACED_EQUIVALENTLY (sauf Naive vs Governed, voir ligne 2) | Le Cockpit F9 est une projection du runtime réel, pas un affichage statique — mais n'a pas repris l'onglet comparatif |
| Packs de tests formels (`resources/proofs/TSS108_ANNEXES...`, `X108_ADVANCED_TESTS_PACK`) | MVP-obsidia- | Annexes constitutionnelles, matrices de sévérité, tests d'ontologie X-108 (ex: `test_absolute_hold_gate.py`, `test_non_invertible_order.py`) | Aucun équivalent direct porté dans `tests/` | NOT_PORTABLE | Ces packs testent des invariants du Kernel X-108 lui-même (ordre non-inversible, hold absolu) — hors périmètre de ce repo puisque le Kernel réel est externe et scellé (cf. `docs/B15_STRUCTURAL_SCORE_BOUNDARY.md`). Pas une perte du domaine Trading, mais une limite structurelle déjà documentée |

**Réponse à la question posée** : la seule propriété utile de MVP-obsidia- qui n'existe plus aujourd'hui dans OBSIDIA_TRADING est le **comparateur "Naive vs Governed"** — repéré et priorisé dans la matrice de migration F0 (`EXTRACT_PATTERN_ONLY`), mais jamais implémenté à travers F1→F9. C'est un gap réel, pas une régression (rien n'a été retiré — il n'a simplement jamais été construit).

## 2. Obsidia-lab-trad / TradingWorld

| Historical Property | Source | Old Implementation | Current Equivalent | Status | Evidence |
|---|---|---|---|---|---|
| Généalogie des 17 agents | Obsidia-lab-trad (mars 2026) | `os4-platform/server/python_agents/domains/trading_agents.py` — 17 agents (MarketData→ProofConsistency) | `native/agents/domains/trading_agents.py` (F3, porté depuis le core actuel) | PRESERVED | `diff` entre les noms de classes du core actuel et de `native/agents/domains/trading_agents.py` → **vide, identique**. Confirmé aussi identique byte-for-byte à Obsidia-lab-trad par l'audit précédent |
| GBM | TradingWorld `tradingEngine.ts` L120 | `gbmReturn = (mu_r-0.5σ²)dt+σ√dt·z` (Box-Muller) | `simulation/trading_world/market_process.py` (F4) | PRESERVED | Formule citée terme à terme dans le code Python, testée dans `tests/unit/test_market_process.py` |
| Régimes de Markov | TradingWorld `tradingEngine.ts` L157-170 | Matrice de transition, auto-transition favorisée artificiellement, **non calibrée sur données réelles** | `simulation/trading_world/market_process.py::build_regime_matrix` (F4) | PRESERVED (avec dette héritée) | **NOT_PORTABLE pour la calibration uniquement** : le module documente explicitement (docstring, lignes 19-21, 65) "NON CALIBREE : la diagonale (auto-transition) est artificiellement favorisée à partir du seed, PAS calibrée". Dette non masquée, héritée intacte de la source TS |
| GARCH(1,1) | TradingWorld `tradingEngine.ts` L108-114 | `garchVar = ω+α·r²+β·garchVar` | `simulation/trading_world/market_process.py` (F4) | PRESERVED | Formule identique, testée (réaction à un choc de volatilité) |
| Jump diffusion (Merton) | TradingWorld `tradingEngine.ts` L122-130 | Poisson + taille de saut, ajoutée au retour GBM | `simulation/trading_world/market_process.py` (F4) | PRESERVED | Formule portée, testée |
| VaR historique | TradingWorld `tradingEngine.ts` L194-197 | Quantile historique des retours triés | `simulation/trading_world/risk_metrics.py` (F4) | PRESERVED | Testé sur séries connues (valeur exacte attendue) |
| Expected Shortfall | TradingWorld `tradingEngine.ts` L198 | Moyenne conditionnelle de queue sous VaR | `simulation/trading_world/risk_metrics.py` (F4) | PRESERVED | Testé |
| Sharpe ratio | TradingWorld `tradingEngine.ts` L200-202 | Rendement annualisé / volatilité annualisée | `simulation/trading_world/risk_metrics.py` (F4) | PRESERVED | Testé |
| Max Drawdown | TradingWorld `tradingEngine.ts` L185-192 | Boucle peak/dd | `simulation/trading_world/risk_metrics.py` (F4) | PRESERVED | Testé |
| Replay seedé déterministe | TradingWorld `tradingEngine.ts` L8-17 | PRNG `mulberry32(seed)` | `simulation/trading_world/rng.py` (F4) | IMPROVED | Réimplanté **fidèlement bit-à-bit** en Python (pas juste "un PRNG seedé équivalent") — testé pour déterminisme strict (même seed → même séquence, seed différente → séquence différente) |
| UI produit (TradingWorld.tsx, dashboard React/Drizzle) | Obsidia-lab-trad | Page produit complète, tick temps réel, scenario runner (7 scénarios) | `apps/cockpit/` (F9) — Streamlit, 8 scénarios, 11 sections | REPLACED_EQUIVALENTLY | Techno différente (Streamlit vs React), mais couverture fonctionnelle équivalente ou supérieure (F9 montre explicitement KX108/Binder/Receipt/Replay, ce que TradingWorld.tsx ne faisait pas — TradingWorld.tsx n'affichait que des métriques agrégées, pas la chaîne de gouvernance) |

## 3. agent-trad-main (source historique la plus importante après le core actuel)

| Historical Property | Source | Old Implementation | Current Equivalent | Status | Evidence |
|---|---|---|---|---|---|
| domain/ports (types + interfaces) | agent-trad-main | `obsidia/domain/*.py`, `obsidia/ports/*.py` | `domain/*.py`, `domain/ports/*.py` (F2) | PRESERVED | COPY_AS_IS, imports réécrits uniquement |
| Architecture hexagonale | agent-trad-main | Perception→Preuve, ports&adapters | Structure identique conservée dans OBSIDIA_TRADING | PRESERVED | Structure de dossiers reproduite |
| CycleEngine | agent-trad-main | `obsidia/runtime/engine.py` | `execution/binder/engine.py` (F3) | PRESERVED | COPY_AS_IS, logique de `_plan()`/`_execute()` intacte caractère pour caractère |
| Bus | agent-trad-main | `obsidia/runtime/bus.py` | `execution/binder/bus.py` (F3) | PRESERVED | COPY_AS_IS |
| Planner | agent-trad-main | `obsidia/runtime/planner.py` | `execution/binder/planner.py` (F3) | PRESERVED | COPY_AS_IS |
| Double barrière d'autorité | agent-trad-main | `authority != ACT ⇒ pas d'action irréversible`, testé 25x | Identique, re-testé (F3, F5, F6, F8.5, F8.6) | IMPROVED | Le principe est préservé et **re-vérifié à chaque phase suivante** (F5 : score local≠autorité ; F6 : Binder indépendant du Bridge ; F8.5/F8.6 : tenu aussi côté externe) — couverture de test bien supérieure à l'original |
| Alpaca PAPER | agent-trad-main | `obsidia/providers/alpaca_*.py` (PASS3) | `market/adapters/alpaca/` (F2) | PRESERVED | COPY_AS_IS, seule source Alpaca de toute la généalogie (confirmé, `ALPACA_RECOVERY_REPORT.md`) |
| Order ledger | agent-trad-main | JSONL, idempotence | `execution/binder/order_ledger_jsonl.py` (F6) | PRESERVED | COPY_AS_IS, exercé dans le scénario de double soumission (F6, F8.5) |
| Idempotence | agent-trad-main | Via order ledger | Identique | PRESERVED | Testé (scénario 6 de F8.5, scénario double soumission F6) |
| Receipt chaining | agent-trad-main | `obsidia/domain/receipt.py::CycleReceipt`, SHA-256 | `domain/receipt.py` (F3), persistance ajoutée (F7) | IMPROVED | Le chaînage existait déjà ; F7 ajoute la persistance durable (JSONL append-only), la détection d'altération et le versionnage de schéma — absents de l'original |
| verify_chain | agent-trad-main | Méthode de vérification en mémoire | `proof/receipts/receipt_verify.py::ReceiptChainVerifier` (F7) | IMPROVED | Détecte maintenant 7 catégories d'altération (modification, suppression, previous_hash invalide, duplicate cycle_id, JSON malformé, chaîne tronquée, version inconnue) contre une vérification en mémoire plus limitée à l'origine |
| Clock déterministe | agent-trad-main | `ClockPort`/`FrozenClock` | `domain/ports/clock.py` (F2) | PRESERVED | COPY_AS_IS |
| Parity/replay | agent-trad-main | `tests/parity.py` (240 cycles, dépendait de `factory.py`/`GuardX108` legacy hors scope) | `proof/receipts/replay.py::ReplayEngine` (F7) — audit + déterministe | REPLACED_EQUIVALENTLY | L'ancien `parity.py` n'a pas pu être porté tel quel (dépendances legacy hors scope, documenté en F3) ; remplacé par un mécanisme de replay plus général (2 niveaux : audit et déterministe MATCH/DIVERGENCE/NOT_REPLAYABLE), testé en F7 et F8.5/F8.6 |
| Score structurel local corrigé (post-B15) | agent-trad-main | `agents/indicators.py::structural_score`, Option C (`A_norm`) | `governance/bridge/local_signal.py::compute_local_structural_signal` (F5) | PRESERVED | Formule portée, **confirmée LOCAL DOMAIN SIGNAL != KX108 AUTHORITY** — attachée uniquement à `Decision.structural_score`, jamais à `Decision.authority` (test `tests/unit/test_governance_bridge.py`, re-confirmé tenir après F6-F9 par les scénarios F8.5 scénario 4 "ACT+Binder refuse" et F8.6) |
| B15 boundary documentée | agent-trad-main | Analyse dans `11_B7_B8_B15_ANALYSIS.md`/`13_POST_B15_FREEZE.md` | `docs/B15_STRUCTURAL_SCORE_BOUNDARY.md` (F5) | IMPROVED | Documente en plus la limite structurelle propre à OBSIDIA_TRADING (calcul de S délégué à un Kernel externe scellé, non vérifiable) — absente du document original car cette limite n'existait pas dans le contexte d'agent-trad-main (qui calculait S en local) |
| Fail-closed | agent-trad-main | HOLD par défaut sur erreur/indisponibilité | `KX108GovernanceBridge` fail-closed sur indisponibilité ET réponse invalide (5 variantes testées) | IMPROVED | Couverture de cas élargie (F5) |
| Monitoring | agent-trad-main | `obsidia/runtime/monitor.py` | `execution/binder/monitor.py` (F2) | PRESERVED | COPY_AS_IS, dépendance directe de `test_alpaca_providers.py` |

## 4. ERC-8004 / legacy intents (archive avril 2026)

| Historical Property | Source | Old Implementation | Current Equivalent | Status | Evidence |
|---|---|---|---|---|---|
| Représentation d'intent | ERC-8004 archive | `blockchain/erc8004_client.py::route_trade_intent(signed_intent: Dict)` — dict signé EIP-712 (`typed_data`, `signature`), couplé à un contrat Solidity Risk Router | `domain/proposal.py` — `TradeIntent`/`AgentOutput` typés, dataclasses immuables, sans dépendance blockchain | REPLACED_EQUIVALENTLY | Le concept "intent avant action" est préservé et plus robuste (typé, testé, indépendant de toute infrastructure blockchain qui n'a jamais été exécutée réellement — `_route_live` confirmé jamais appelé en conditions réelles par l'audit initial) |
| Sémantique temporelle | ERC-8004 archive | Pas de mécanisme temporel dédié observé dans le client (timestamp brut dans le dict) | `SourceProvenance.observed_at`/`ingested_at` (F7.5) + `Provenance.fetched_at` (F2) | IMPROVED | Distinction explicite observé/ingéré, absente de l'original |
| Identité externe / concepts de requête | ERC-8004 archive | `register_identity(profile)` — identité on-chain via Identity Registry (jamais exécuté réellement, stub) | `SourceProvenance.source_id`/`organization_id`/`adapter_id` (F7.5), `ExternalSignal` (F8) | REPLACED_EQUIVALENTLY | Le concept d'identité de source externe est préservé sans la dépendance blockchain non fonctionnelle ; testé bout-en-bout (F8.6, provenance intacte après reload) |
| Auditabilité | ERC-8004 archive | `submit_validation(artifact)` — soumission à un Validation Registry externe (stub) | `CycleReceipt` chaîné + `ReceiptStore` + `ReceiptChainVerifier` (F3/F7) | IMPROVED | Le nouveau mécanisme d'auditabilité est réellement fonctionnel et testé (hash-chain, détection d'altération), contrairement au registre blockchain qui n'a jamais tourné en conditions réelles |

**Note** : conformément à la consigne, aucune recommandation de réintroduire le contrat Solidity/Sepolia n'est faite — il reste `KEEP_REFERENCE_ONLY`/`REJECT` comme établi dans `TRADING_MIGRATION_MATRIX.md` de l'audit F0.

## 5. Core actuel trading agents vs roster porté

| Vérification | Résultat |
|---|---|
| Noms des 17 classes d'agents | **Identiques** — `diff` entre `sigma/domains/trading_agents.py` (core, relu à l'instant) et `native/agents/domains/trading_agents.py` (F3) → vide |
| Rôles | Identiques (même fichier, COPY_AS_IS confirmé) |
| Outputs (AgentOutput) | Identiques — et depuis F7.5/F8.7, le chemin natif passe désormais par le même `to_canonical_agent_signal` que l'externe (amélioration post-portage, pas une divergence avec le core) |
| unknowns/contradictions/risk_flags/evidence | Préservés — champs de première classe depuis F3.5, aucune perte confirmée par `tests/unit/test_canonical_contract_integrity.py` et `test_source_provenance.py` |
| Nouvelle capacité du Core absente de native/agents/ | **Aucune détectée** à ce jour de relecture (2026-09-21) — le fichier du core relu à l'instant est identique à celui porté en F3. Si le core évolue après cette date, une nouvelle vérification sera nécessaire (pas de mécanisme de synchronisation automatique entre les deux) |

## 6. Régression runtime

```
pytest tests/ -q
168 passed, 1 skipped in 4.62s
```

**Résultat exact, aucune régression** — identique au point de départ documenté à la fin de F9.

## 7. Couverture des scénarios de non-régression

| Scénario | Test exact |
|---|---|
| Native ACT | `tests/integration/test_end_to_end_full_stack.py` (scénario 1, avec simulation) |
| Native HOLD | `tests/integration/test_end_to_end_full_stack.py` (scénario 2) |
| Native BLOCK | `tests/integration/test_end_to_end_full_stack.py` (scénario 3) |
| External ACT | `tests/integration/test_end_to_end_external_full_stack.py` (scénario ACT+simulation) |
| External BLOCK | `tests/integration/test_end_to_end_external_full_stack.py` (scénario BLOCK) |
| Binder refusal | `tests/integration/test_end_to_end_full_stack.py` (scénario 4, ACT+Binder refuse) |
| Broker failure | `tests/integration/test_end_to_end_full_stack.py` (scénario 5) et `tests/integration/test_paper_execution_pipeline.py` (F6, scénario 7) |
| Duplicate intent / idempotence | `tests/integration/test_end_to_end_full_stack.py` (scénario 6) et `tests/integration/test_paper_execution_pipeline.py` (F6, scénario 8) |
| Simulation deterministic MATCH | `tests/integration/test_end_to_end_full_stack.py` (replay déterministe, même seed) et `tests/unit/test_replay.py` (F7) |
| Receipt corruption detection | `tests/unit/test_receipt_chain.py` (F7, tests 3-7) et `tests/integration/test_end_to_end_full_stack.py` (altération volontaire sur copie) |
| Audit Replay | `tests/unit/test_replay.py` (F7) + scénario 1 de F8.5/F8.6 |
| Deterministic Replay | `tests/unit/test_replay.py` (F7) + scénario 1 de F8.5/F8.6 |
| Native/External canonical convergence | `tests/integration/test_end_to_end_full_stack.py` (scénario 7, F8.5) et `tests/unit/test_canonical_convergence.py` (F8.7) |

**13/13 scénarios confirmés couverts, aucun manquant.**

## Synthèse chiffrée

| Statut | Compte |
|---|---|
| TOTAL_PROPERTIES | 39 |
| PRESERVED | 20 |
| IMPROVED | 12 |
| REPLACED_EQUIVALENTLY | 6 |
| INTENTIONALLY_DROPPED | 0 |
| MISSING | 1 (Naive vs Governed, MVP-obsidia-) |
| NOT_PORTABLE | 2 (packs de tests formels Kernel, MVP-obsidia- ; calibration Markov, TradingWorld — dette héritée documentée) |
| **REGRESSIONS** | **0** |

## Réponse explicite

**REGRESSION = 0 : OUI, confirmé.** Aucune propriété historique testée n'a régressé. Une seule propriété utile (Naive vs Governed) est absente — c'est un **gap de construction** (jamais implémenté malgré avoir été priorisé dès F0), pas une perte (rien n'a existé puis disparu dans OBSIDIA_TRADING). Deux limites sont héritées et documentées explicitement comme non portables pour des raisons structurelles (Kernel scellé externe ; calibration de marché nécessitant des données réelles).

**Statut F10.1 : DONE.**
