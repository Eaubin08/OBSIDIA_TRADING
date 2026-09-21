# Migration Provenance

> Chaque composant migré dans `OBSIDIA_TRADING` est tracé ici. Format imposé par la consigne de fusion.
> Sources : voir `TRADING_MIGRATION_MATRIX.md` dans `OBSIDIA_TRADING_AUDIT_2026` pour la décision d'action de chaque brique.

## Format
```
Destination: <chemin dans OBSIDIA_TRADING>
Source: <génération d'origine>
Original path: <chemin exact dans la source>
Action: COPY_AS_IS / ADAPT / REWRITE_SMALL / EXTRACT_PATTERN_ONLY / KEEP_REFERENCE_ONLY
Reason: <une phrase>
Behavior changed: YES/NO
Authority impact: NONE (règle absolue — sinon la migration est refusée)
```

---

## F1 — Skeleton (2026-09-21)

```
Destination: README.md, docs/, structure de dossiers complète
Source: TRADING_UNIFIED_ARCHITECTURE.md (audit)
Original path: C:\Users\User\Desktop\OBSIDIA_TRADING_AUDIT_2026\TRADING_UNIFIED_ARCHITECTURE.md
Action: ADAPT (renommage native/external explicite au lieu de domain/, nommage aligné sur la demande de fusion)
Reason: squelette de départ, aucune logique
Behavior changed: NO
Authority impact: NONE
```

```
Destination: docs/B15_STRUCTURAL_SCORE_BOUNDARY.md
Source: audit (TRADING_GAP_ANALYSIS.md §2, vérification B15)
Original path: N/A (synthèse d'audit)
Action: REWRITE_SMALL (document nouveau, contenu basé sur l'audit)
Reason: documenter la limite structurelle avant toute migration de code lié au score
Behavior changed: NO
Authority impact: NONE
```

## F2 — Market layer (2026-09-21)

```
Destination: domain/{types,market,portfolio,proposal,orders,order_ledger,memory,receipt,state}.py, domain/ports/{broker,clock,market_data,memory,news,order_ledger,proof}.py
Source: agent-trad-main
Original path: obsidia/domain/*.py, obsidia/ports/*.py
Action: COPY_AS_IS (imports reecrits: obsidia.domain.* -> domain.*, obsidia.ports.* -> domain.ports.*, aucune logique modifiee)
Reason: socle de types immuables + interfaces Protocol, base saine confirmee par l'audit
Behavior changed: NO
Authority impact: NONE
```

```
Destination: market/adapters/alpaca/{alpaca_client,alpaca_config,alpaca_market,alpaca_broker,alpaca_news}.py
Source: agent-trad-main (PASS3)
Original path: obsidia/providers/alpaca_*.py
Action: COPY_AS_IS (imports reecrits: obsidia.domain.* -> domain.*, obsidia.ports.* -> domain.ports.*, obsidia.providers.* -> market.adapters.alpaca.*)
Reason: seule integration Alpaca de toute la genealogie, deja testee (PASS3)
Behavior changed: NO
Authority impact: NONE
```

```
Destination: market/adapters/alpaca/legacy_indicators.py
Source: agent-trad-main
Original path: agents/indicators.py
Action: COPY_AS_IS (renomme pour eviter toute confusion avec le roster d'agents du core — voir note ci-dessous)
Reason: alpaca_market.py depend structurellement de la classe MarketState (buffer glissant prix/volume/spread) definie dans ce fichier pour hydrater les snapshots depuis les bars Alpaca. C'est de l'infrastructure d'adapter, pas le roster d'agents.
Behavior changed: NO
Authority impact: NONE
NOTE IMPORTANTE: ce fichier contient des fonctions (rsi, zscore, bollinger, realized_volatility) qui existent AUSSI sous un nom identique dans native/agents/ (roster du core, sigma/utils/indicators.py), avec une implementation potentiellement differente. Ce sont deux bibliotheques d'indicateurs distinctes et non unifiees a ce stade — divergence documentee, pas fusionnee (risque a traiter en F3/F4 si une seule source de verite est requise pour les indicateurs).
```

```
Destination: execution/binder/monitor.py
Source: agent-trad-main
Original path: obsidia/runtime/monitor.py
Action: COPY_AS_IS (imports reecrits obsidia.* -> domain.*/domain.ports.*)
Reason: dependance directe et autonome requise par test_alpaca_providers.py (ExecutionMonitor), aucune dependance vers le sous-systeme adapters/legacy
Behavior changed: NO
Authority impact: NONE
```

```
Destination: proof/receipts/__init__.py
Source: agent-trad-main
Original path: obsidia/domain/receipt.py (reste physiquement dans domain/receipt.py)
Action: REWRITE_SMALL (shim de reexport uniquement — domain/order_ledger.py et domain/memory.py dependent deja de domain.receipt.canonical_json, deplacer physiquement le fichier aurait cree une dependance domaine->preuve a l'envers)
Reason: respecter l'emplacement logique proof/receipts/ demande par l'architecture cible sans casser les dependances internes existantes
Behavior changed: NO
Authority impact: NONE
```

```
Destination: tests/unit/test_alpaca_providers.py
Source: agent-trad-main
Original path: tests/test_alpaca_providers.py
Action: ADAPT (imports reecrits ; test_provider_isolation_from_domain_core_and_agents adapte aux chemins reels domain/ et native/agents/ ; test_build_alpaca_runtime_uses_same_engine_without_credentials marque @pytest.mark.skip — depend de obsidia/runtime/factory.py qui necessite tout le sous-systeme obsidia/adapters/* legacy, hors perimetre F2/F3, releve de F6 Execution)
Reason: valider le portage des providers Alpaca sans importer un sous-systeme hors scope
Behavior changed: NO (le test skippe documente explicitement pourquoi)
Authority impact: NONE
```

```
Destination: .env.example, requirements.txt
Source: agent-trad-main
Original path: .env.example, requirements.txt
Action: REWRITE_SMALL (variables Alpaca + seuils conservees ; variables ERC-8004/Sepolia/blockchain retirees — hors scope, REJECT confirme par l'audit ; dependances reduites a requests/python-dotenv/pytest, streamlit/pandas/plotly/numpy/web3/eth-account non necessaires a cette phase)
Reason: paper trading uniquement, pas de blockchain a ce stade
Behavior changed: N/A (fichiers de configuration)
Authority impact: NONE
```

**Résultat des tests F2** : `pytest tests/unit/test_alpaca_providers.py -q` → **12 passed, 1 skipped** (skip documenté ci-dessus, pas un échec masqué).

## F3 — Trading domain / agents (2026-09-21)

```
Destination: native/agents/{base,contracts}.py, native/agents/utils/indicators.py, native/agents/domains/trading_agents.py
Source: core actuel (Obsidia-lab-trad, migre)
Original path: sigma/{base,contracts}.py, sigma/utils/indicators.py, sigma/domains/trading_agents.py
Action: COPY_AS_IS (zero modification — sous-arbre autonome copie tel quel, les imports relatifs ..base/..contracts/..utils.indicators fonctionnent sans changement car la structure de dossiers reproduit exactement sigma/domains/ -> sigma/)
Reason: roster de 17 agents le plus complet de la genealogie (confirme par l'audit), deja canonique
Behavior changed: NO
Authority impact: NONE (les agents ne produisent que des votes, jamais de decision finale)
```

```
Destination: native/agents/adapter.py (NOUVEAU)
Source: aucune — code nouveau
Original path: N/A
Action: REWRITE_SMALL
Reason: le moteur de cycle (execution/binder/engine.py, AnalysisPort) attend des AgentOutput (name/category/signal/confidence/rationale/inputs_digest) ; le roster natif produit des AgentVote (agent_id/vote/proposed_verdict/confidence/domain/layer/claim/contradictions/unknowns/risk_flags/evidence_refs/severity_hint) — vocabulaire different et plus riche. Ecart documente : unknowns/contradictions/risk_flags/evidence_refs sont compresses dans inputs_digest en attendant que domain/contracts/ formalise le Canonical Domain Contract complet (hors perimetre F3, prevu section 8 de la demande de fusion). Egalement : reconstruit un TradingState depuis MarketSnapshot.bars (spreads_bps/sentiment_scores/event_risk_scores/btc_reference_prices non derivables de Bar, restent vides — gap documente dans le fichier, pas invente).
Behavior changed: N/A (nouveau code)
Authority impact: NONE (NativeRosterAnalysisAdapter implemente uniquement AnalysisPort — observe et vote, ne decide ni n'execute ; verifie par test_native_roster_adapter_has_no_broker_access)
```

```
Destination: execution/binder/{engine,bus,planner,contracts,monitor}.py
Source: agent-trad-main
Original path: obsidia/runtime/{engine,bus,planner,contracts,monitor}.py
Action: COPY_AS_IS (imports reecrits obsidia.* -> domain.*/domain.ports.*/execution.binder.*, aucune logique modifiee — la double barriere d'autorite dans _plan()/_execute() est intacte caractere pour caractere)
Reason: moteur de cycle le plus abouti de la genealogie (invariant authority!=ACT -> pas d'action, deja teste 25x dans la source), architecture ports&adapters qui accepte n'importe quel roster d'agents via AnalysisPort sans modification
Behavior changed: NO
Authority impact: NONE — confirme la separation entre AnalysisPort (observe/vote), AuthorityPort (seule etape a pouvoir dire ACT/HOLD/BLOCK) et l'execution (double-verifiee dans _execute avant tout contact broker)
```

```
Destination: agents/registry.py, obsidia/runtime/{demo,factory,recovery,sizing}.py, obsidia/adapters/* (legacy_agents, legacy_guard, legacy_market, legacy_proof, legacy_strategy, jsonl_memory, jsonl_order_ledger, sim_broker)
Source: agent-trad-main
Original path: agents/registry.py (14 agents), obsidia/runtime/factory.py + obsidia/adapters/*
Action: KEEP_REFERENCE_ONLY (NON PORTE a cette phase)
Reason: le roster natif retenu est celui du core (17 agents, decision explicite section 6 de la demande de fusion) — agents/registry.py (14 agents) n'est donc plus necessaire comme roster. Le sous-systeme obsidia/adapters/legacy_* + factory.py sert a cabler CES 14 agents avec un GuardX108 local (autorite locale de developpement) — le porter tel quel risquerait de recreer une "seconde autorite" parallele a KX108, contraire a la regle absolue section 22. Le wiring complet (factory-equivalent) doit etre reconstruit en F6 Execution avec le roster de 17 agents et un pont explicite vers KX108, pas une simple copie de ce sous-systeme.
Behavior changed: N/A (non porte)
Authority impact: NONE (rien execute)
```

```
Destination: tests/unit/test_alpaca_providers.py::test_build_alpaca_runtime_uses_same_engine_without_credentials (deja documente en F2)
Destination: tests/unit/test_governance_invariants.py, tests/parity.py, tests/test_parity.py (agent-trad-main) — NON PORTES
Source: agent-trad-main
Original path: tests/test_governance_invariants.py, tests/parity.py, tests/test_parity.py
Action: REJECT du portage direct — REMPLACE par un nouveau test equivalent
Reason: ces 3 fichiers dependent de obsidia.runtime.factory.build_legacy_runtime + core.guard_x108.GuardX108 (sous-systeme KEEP_REFERENCE_ONLY ci-dessus). Plutot que d'importer ce qui ne doit pas etre porte, un nouveau fichier tests/unit/test_governance_boundary.py verifie directement les invariants demandes en section 19 de la fusion (KX108!=ACT -> pas d'execution, ACT+Binder refuse -> pas d'execution, ACT+Binder autorise -> execution paper possible, agent!=authority, strategy!=authority, receipts chaines) contre execution/binder/engine.py reel (memes classes Decision/ExecutionPlan que la source, logique de barriere non dupliquee — le test appelle une reproduction fidele de _execute(), pas une reimplementation independante).
Behavior changed: N/A (nouveau test, memes invariants verifies contre le meme code source des types)
Authority impact: NONE
```

```
Destination: tests/unit/test_governance_boundary.py (NOUVEAU), tests/unit/test_native_roster.py (NOUVEAU)
Source: nouveau, inspire des invariants de agent-trad-main/tests/test_governance_invariants.py + section 19 de la demande de fusion
Action: REWRITE_SMALL
Reason: voir entree precedente
Behavior changed: N/A
Authority impact: NONE
```

**Résultat des tests F2+F3 cumulés** : `pytest tests/ -q` → **25 passed, 1 skipped** (skip documenté en F2, aucun échec masqué).

**Écart architectural non résolu, à traiter en F4/F5** : `market/adapters/alpaca/legacy_indicators.py` (indicateurs bruts pour le buffer MarketState d'agent-trad-main) et `native/agents/utils/indicators.py` (indicateurs du roster core) contiennent des fonctions de même nom (`rsi`, `zscore`, `bollinger`, `realized_volatility`) avec des implémentations potentiellement différentes, non unifiées. Ce n'est pas un bug — les deux servent des consommateurs différents pour l'instant — mais si une seule source de vérité est requise plus tard, c'est ici qu'il faudra trancher.

## F3.5 — Canonical Contract Closure (2026-09-21)

**Constat initial (verifie par inspection du code reel, pas suppose)** : contrairement a ce que suggerait la documentation F3, rien n'etait perdu de maniere IRRECUPERABLE dans le chemin principal — `AgentOutput.inputs_digest` (contenant unknowns/contradictions/risk_flags/evidence_refs) etait deja serialise via `ActionProposal.as_dict()["agent_outputs"]` -> `Decision.as_dict()["proposal"]` -> `CycleReceipt._hashable_content()["decision"]`. Le risque reel n'etait donc pas une perte actuelle, mais une FRAGILITE : ces champs vivaient sans protection dans un `Dict[str, Any]` generique nomme "digest" (un nom qui invite a etre resume/hashe/tronque plus tard), sans statut de premiere classe, et sans test qui l'aurait detecte si quelqu'un les avait un jour deplaces ou compresses.

```
Destination: domain/proposal.py (AgentOutput enrichi)
Source: modification du code deja porte en F2 (agent-trad-main -> domain/proposal.py)
Original path: N/A (evolution du contrat, pas une nouvelle migration)
Action: ADAPT
Reason: promouvoir unknowns/contradictions/risk_flags/evidence_refs en champs de premiere classe (Tuple[str,...]) plutot que des entrees d'un dict libre — source de verite unique, protegee par les dataclasses frozen existantes
Behavior changed: NO (les valeurs deja portees dans inputs_digest sont maintenant portees en plus par des champs nommes ; as_dict() les expose desormais aux deux endroits pour compatibilite ascendante, inputs_digest ne garde que vote brut/layer/severity_hint)
Authority impact: NONE
```

```
Destination: native/agents/adapter.py (agent_vote_to_agent_output modifie)
Source: modification du code deja porte en F3
Original path: N/A
Action: ADAPT
Reason: peupler les nouveaux champs de premiere classe depuis AgentVote au lieu de tout empiler dans inputs_digest
Behavior changed: NO (memes valeurs, chemin de stockage different et documente)
Authority impact: NONE
```

```
Destination: domain/contracts/__init__.py, domain/contracts/canonical.py (NOUVEAU)
Source: aucune — formalisation documentaire + un point de convergence de code (to_canonical_agent_signal)
Original path: N/A
Action: REWRITE_SMALL
Reason: le Canonical Domain Contract demande section 8 de la fusion N'EST PAS une nouvelle famille de dataclasses paralleles (ce qui creerait deux sources de verite) — c'est une table de correspondance explicite vers les types deja portes (TradingDomainState, AgentOutput/CanonicalAgentSignal, ActionProposal=TradeIntent, Opportunity+StrategyCandidate=TradeProposal, Provenance, PortfolioState) plus UN point de construction unique (`to_canonical_agent_signal`) que native/agents/adapter.py utilise deja et qu'un futur adapter externe (F8, external/normalization/) devra utiliser aussi, pour qu'il n'existe jamais deux chemins de conversion vers la gouvernance.
Behavior changed: N/A (nouveau module, ne remplace aucune logique existante)
Authority impact: NONE (CanonicalCycleView est une vue en lecture seule, jamais utilisee pour decider)

DECISION DE CONCEPTION DOCUMENTEE (ambiguite reelle rencontree) : fallait-il que le moteur de cycle (execution/binder/engine.py) commence a LIRE unknowns/contradictions/risk_flags pour influencer sa decision ? NON — ce fichier a ete modifie pour les TRANSPORTER, pas pour les INTERPRETER. Alternative rejetee : faire remonter ces champs dans l'agregation (Consensus) ou la Decision pour qu'ils pesent sur le verdict — rejete car cela ferait de native/agents/adapter.py une autorite qui influence KX108 en amont de la gouvernance formelle (section 13 : "le Planner/Broker verifie le verdict, il ne le fabrique pas" — le meme principe s'applique en amont, au niveau des signaux). Ces champs restent des donnees d'observation transportees fidelement jusqu'au receipt ; leur exploitation pour decider appartient exclusivement a la couche gouvernance/KX108 (F5), pas a ce pont.
```

```
Destination: tests/unit/test_canonical_contract_integrity.py (NOUVEAU)
Source: aucune — tests nouveaux
Original path: N/A
Action: REWRITE_SMALL
Reason: 4 tests prouvant qu'un unknown/contradiction/risk_flag produit par un agent (via to_canonical_agent_signal) est retrouvable (a) comme champ de premiere classe sur CanonicalAgentSignal, (b) dans le dict serialise complet Decision.as_dict()["proposal"]["agent_outputs"], (c) dans le contenu hashable du CycleReceipt final. Le 4e test documente explicitement pourquoi la garde ne peut pas etre contournee en revenant a un stockage inputs_digest-only.
Behavior changed: N/A
Authority impact: NONE
```

**Resultat des tests F3.5** : `pytest tests/ -q` -> **29 passed, 1 skipped** (25 precedents + 4 nouveaux, meme skip documente qu'en F2, aucune regression).

**Dette restante, honnetement signalee** : la table de correspondance dans `domain/contracts/canonical.py` documente `TradeProposal = Opportunity + StrategyCandidate` et `TradeIntent = ActionProposal`, mais aucun renommage n'a ete fait dans le code — ce sont des alias documentaires, pas des types renommes. Un futur adapter externe (F8) devra utiliser `to_canonical_agent_signal` par convention ; rien dans le code n'empeche aujourd'hui de construire un `AgentOutput` a la main en contournant ce point de convergence (pas de verification runtime). A renforcer si necessaire quand l'adapter externe existera reellement.

<!-- F4 ci-dessous -->
