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

## F4 — Simulation (2026-09-21)

```
Destination: simulation/monte_carlo/bootstrap.py
Source: MVP-obsidia- (clone temporaire, non permanent)
Original path: src/simulation/sim_lite.py (fonctions sim_lite_bootstrap, max_drawdown_from_returns)
Action: EXTRACT_PATTERN_ONLY (logique portee fidelement, dataset factice BTC_1h.csv NON porte — le module accepte n'importe quelle serie de retours numpy reelle)
Reason: seul bootstrap Monte Carlo reel confirme par l'audit (pas de mock), hypothese-free (rien de parametrique, reechantillonne l'historique tel quel)
Behavior changed: NO pour la logique de calcul (formules identiques) ; ADAPT mineur = parametre `seed` optionnel ajoute (source originale utilisait np.random global non seede) pour permettre la reproductibilite quand elle est demandee
Authority impact: NONE (produit des metriques statistiques, ne decide et n'execute rien)
```

```
Destination: simulation/trading_world/{rng.py, market_process.py, risk_metrics.py}
Source: Obsidia-lab-trad (clone temporaire, non permanent)
Original path: os4-platform/server/engines/tradingEngine.ts (223 lignes, verifie ligne par ligne par audit prealable — 9/9 modeles confirmes reels, aucun factice)
Action: REWRITE_SMALL (reecriture Python fidele, PAS un portage TypeScript->Python litteral ; formules mathematiques identiques, structure de donnees adaptee — dataclasses au lieu d'interfaces TS)
Reason: seul moteur de simulation parametrique confirme par lecture de code (GBM regime-dependant + Markov + GARCH(1,1) + jump diffusion de Merton + VaR/ES/Sharpe/MaxDrawdown + PRNG seede)
Behavior changed: NON pour les formules (portees terme a terme, citees en commentaire dans chaque fonction) ; le PRNG mulberry32 a ete reimplemente en arithmetique 32 bits non signee Python plutot que remplace par random.Random/numpy.default_rng — la consigne n'exigeait pas la fidelite bit-a-bit mais elle etait peu couteuse a obtenir (8 lignes) et evite d'introduire une 3e famille de PRNG dans l'ecosysteme ; garantie de determinisme (meme seed -> meme sequence exacte) verifiee par test, pas supposee
Authority impact: NONE (produit une trajectoire de prix simulee et des metriques, ne decide et n'execute rien — verifie par absence d'import vers execution.binder/market.adapters.alpaca dans tout le module)
```

**AVERTISSEMENT explicitement documente et repris tel quel de la source** : `build_regime_matrix` (simulation/trading_world/market_process.py) genere une matrice de transition de Markov a partir du seed, PAS calibree sur des donnees de marche reelles (meme limite que la source TS — l'audit prealable l'avait deja signalee). Docstring du module + present rapport = double documentation intentionnelle.

**Comparaison Monte Carlo (MVP) vs TradingWorld engine — decision documentee** :
- `simulation/monte_carlo/bootstrap.py` (MVP) : **hypothese-free**, reechantillonne une serie de retours REELLE fournie en entree — pas de modele de marche suppose, juste l'historique lui-meme.
- `simulation/trading_world/` (Obsidia-lab-trad) : **parametrique**, genere des trajectoires SYNTHETIQUES a partir d'hypotheses de modele (GBM+regimes+GARCH+jumps) — utile pour des scenarios "et si" (stress test, absence de donnees historiques suffisantes, calibration de seuils avant d'avoir un historique reel).
- **Decision** : les deux sont **COMPLEMENTAIRES**, pas redondants — aucun n'est designe "moteur principal" au detriment de l'autre. `monte_carlo/` est le choix par defaut des qu'un historique de marche reel est disponible (ex: donnees Alpaca deja portees en F2). `trading_world/` est le choix pour un stress test parametrique controle (flash crash simule, regime de marche hypothetique) ou en l'absence de donnees historiques suffisantes. Les deux alimentent le domaine/la preuve en scenarios et metriques, jamais l'execution directement.

```
Destination: tests/unit/{test_market_process.py, test_monte_carlo_bootstrap.py}
Source: nouveaux tests
Original path: N/A
Action: REWRITE_SMALL
Reason: couverture explicite exigee — un test par modele (GBM, GARCH, jumps, Markov), cas de calcul exacts connus a la main pour VaR/ES/Sharpe/MaxDrawdown/Merkle, et 4 tests de determinisme (meme seed -> sequence identique stricte, seed different -> sequence differente, PRNG et Box-Muller reproductibles isolement)
Behavior changed: N/A
Authority impact: NONE
```

**Resultat des tests F4** : `pytest tests/ -q` -> **59 passed, 1 skipped** (29 precedents + 30 nouveaux, meme skip documente depuis F2, aucune regression). Un echec initial (`test_garch_reacts_to_volatility_shock`) etait un bug dans l'hypothese du test lui-meme (l'etat initial suppose etait faux — le moteur applique bien la mise a jour GARCH des t=0, fidele a la source), corrige avant ce rapport, pas dans le moteur porte.

**Differences avec les versions historiques** : requirements.txt enrichi de `numpy>=1.26.0` (necessaire pour le bootstrap, absent jusqu'ici). Aucune autre dependance nouvelle. Aucun acces broker ni capacite de decision dans simulation/ — verifie par grep, aucun import vers execution.binder ou market.adapters.alpaca.

**Statut F4 : DONE.**

**Prochain verrou avant F5 (Governance Bridge)** : F5 doit brancher TradeIntent vers l'interface KX108 — mais docs/B15_STRUCTURAL_SCORE_BOUNDARY.md documente deja que le score structurel ne peut pas etre verifie contre le Kernel reel depuis ce repo (calcul delegue a un Kernel externe scelle). Avant de commencer F5, une decision utilisateur explicite est necessaire : (a) obtenir l'acces en lecture au Kernel X-108 reel pour verifier la formule, ou (b) accepter la version corrigee d'agent-trad-main (deja documentee comme reference locale, jamais autorite) comme signal canonique du domaine independamment du Kernel de production actuel. Sans cette decision, F5 risquerait de batir un "governance bridge" vers une formule dont le comportement reel cote Kernel reste inconnu.

**Decision utilisateur recue (2026-09-21)** : option (b), avec regle stricte explicite — le score local est un signal/evidence, jamais une autorite ; KX108 reste la seule source du verdict ; fail-closed si KX108 indisponible/invalide. F5 execute cette regle ci-dessous.

## F5 — Governance Bridge (2026-09-21)

**Architecture implementee** (imposee par l'utilisateur, aucune deviation) :
```
Trading Domain (Agents/Simulation/Local signals)
  -> Canonical DomainState + TradeIntent (ActionProposal, deja porte F2/F3)
  -> Governance Bridge (NOUVEAU)
  -> KX108 (KX108Client, interface — pas de vrai Kernel accessible)
  -> Canonical Decision (Authority ACT/HOLD/BLOCK, deja porte F2)
  -> Binder (execution/binder/engine.py, deja porte F3 — AUCUNE MODIFICATION)
  -> Execution (market/adapters/alpaca, deja porte F2)
```

```
Destination: governance/bridge/local_signal.py (NOUVEAU)
Source: agent-trad-main
Original path: agents/indicators.py (triangle_mean, asymmetry_penalty, structural_score), core/guard_x108.py (_build_coherence_matrix)
Action: COPY_AS_IS (formule mathematique triangle_mean/asymmetry_penalty/structural_score, deja post-B15 Option C, identique caractere pour caractere) + ADAPT (build_coherence_matrix : meme algorithme, entree changee de l'ancien AgentVote.signal/.confidence du prototype 14-agents vers domain.proposal.AgentOutput.signal/.confidence du roster natif 17-agents deja porte en F3)
Reason: seule formule structurelle corrigee (post-B15) de toute la genealogie ; necessaire comme evidence locale transportee, jamais comme autorite (voir docs/B15_STRUCTURAL_SCORE_BOUNDARY.md)
Behavior changed: NO pour la formule (meme calcul) ; le type d'entree change (AgentOutput au lieu d'AgentVote du prototype) car c'est le seul roster porte dans ce repo
Authority impact: NONE — LocalStructuralSignal.S n'est jamais lu par governance_bridge.py pour determiner Decision.authority, uniquement attache a Decision.structural_score (deja un champ existant de domain/receipt.py::Decision depuis F2)
NOTE IMPORTANTE (correction d'une erreur de documentation F1) : docs/B15_STRUCTURAL_SCORE_BOUNDARY.md annoncait initialement ce fichier a native/indicators/structural_score.py — ce chemin n'a jamais ete cree en F2/F3/F4 (seuls legacy_indicators.py et native/agents/utils/indicators.py, qui ne portent PAS structural_score, l'ont ete). Le fichier reel est governance/bridge/local_signal.py, cree ici en F5 et non avant. Le document B15 a ete corrige en consequence.
```

```
Destination: governance/bridge/kx108_client.py (NOUVEAU)
Source: aucune — interface nouvelle, inspiree du contrat reel du core actuel
Original path: N/A (contrat inspire de obsidia-x108-proofs_REMOTE_A5F21C6B/domains/trading/trading_x108_gate.py, lu en lecture seule, jamais copie)
Action: REWRITE_SMALL
Reason: aucun vrai Kernel X-108 n'est accessible depuis ce repo (fait acquis, pas re-verifie) ; un Protocol KX108Client + UnavailableKX108Client (comportement honnete par defaut) + doubles de test (StaticKX108Client, RaisingKX108Client) permettent de construire et tester le bridge sans jamais simuler un Kernel qui n'existe pas
Behavior changed: N/A (nouveau code)
Authority impact: NONE (UnavailableKX108Client leve systematiquement une exception, jamais un verdict invente)
```

```
Destination: governance/bridge/ir_payload.py (NOUVEAU)
Source: format de payload inspire de obsidia-x108-proofs_REMOTE_A5F21C6B/domains/trading/trading_x108_gate.py::translate_to_ir (lecture seule, core actuel, jamais modifie)
Original path: N/A (schema domain/data:{T_mean,H_score,A_score,S}/meta reproduit a l'identique ; bloc "evidence" ajoute, absent de la source)
Action: REWRITE_SMALL
Reason: reutiliser le seul contrat KX108 connu et averti (celui du gate reel) plutot que d'en inventer un nouveau est le choix le plus honnete ; le bloc evidence (unknowns/contradictions/risk_flags/evidence_refs/portfolio_context) est un ajout additif, documente comme non consomme par la decision, pour respecter la regle de non-perte semantique (F3.5) jusque dans l'appel KX108 lui-meme
Behavior changed: N/A (nouveau code, aucune source executable modifiee)
Authority impact: NONE
```

```
Destination: governance/bridge/governance_bridge.py (NOUVEAU)
Source: aucune — nouveau code, implemente le Protocol AuthorityPort deja defini dans execution/binder/contracts.py (F3, non modifie)
Original path: N/A
Action: REWRITE_SMALL
Reason: KX108GovernanceBridge.evaluate() est LE point d'injection dans CycleEngine (execution/binder/engine.py, parametre constructeur `authority: AuthorityPort`, ligne 262 : `self.authority.evaluate(proposal, state, decision_id)`) — aucune modification du moteur n'a ete necessaire, l'injection existait deja depuis F3
Behavior changed: N/A (nouveau code) ; execution/binder/engine.py : AUCUNE MODIFICATION (0 ligne touchee)
Authority impact: NONE — verifie explicitement par 7 tests obligatoires (voir tests/unit/test_governance_bridge.py) : score local eleve+BLOCK->pas d'execution, score local eleve+HOLD->pas d'execution, score local faible+ACT->Binder reste libre de refuser, KX108 indisponible->fail-closed HOLD, reponse invalide->fail-closed HOLD (5 variantes), aucun import direct domain/native/simulation->execution.binder, aucun import direct governance.bridge->broker/alpaca
```

**Resultat des tests F5** : `pytest tests/ -q` -> **71 passed, 1 skipped** (59 precedents + 12 nouveaux, meme skip documente depuis F2, aucune regression). Un test structurel (`test_no_direct_import_from_domain_or_agents_or_simulation_to_binder`) a d'abord echoue sur un faux positif : le docstring de `simulation/trading_world/__init__.py` (F4) mentionne la phrase "execution.binder" en prose pour documenter l'interdiction, ce qui declenchait une simple recherche de sous-chaine. Corrige en filtrant sur les lignes `import`/`from ... import` reelles, pas le contenu textuel complet — pas un defaut du code F4, un defaut du test lui-meme.

**Chemins d'autorite prouves par les tests** :
- `ActionProposal` (Domain/Agents/Simulation) ne peut atteindre `execution/binder` que via une instance de `AuthorityPort` injectee — aucun module de `domain/`, `native/agents/`, `simulation/` n'importe `execution.binder` directement (test structurel 6)
- `governance/bridge/` ne peut atteindre le broker/Alpaca que via `Decision.authority` transmise au Binder deja existant — aucun import direct vers `market.adapters.alpaca` ni `execution.binder`, aucun appel `.submit()` (test structurel 7)
- Le score structurel local ne peut jamais devenir une autorite : `Decision.authority` provient exclusivement de `response["verdict"]` du `KX108Client` ; `LocalStructuralSignal.S` n'alimente que `Decision.structural_score` (jamais lu par la logique de parsing d'autorite)

**Comportements fail-closed garantis** :
- `KX108Unavailable` ou toute exception inattendue levee par le client -> `Authority.HOLD`, `metrics["fail_closed"] = True`
- Reponse KX108 sans cle `"verdict"`, verdict de type incorrect, valeur inconnue, ou reponse non-dict -> `Authority.HOLD`, `metrics["fail_closed"] = True` (5 variantes testees explicitement)
- Dans les deux cas, `Decision.structural_score` reste renseigne (le signal local voyage jusqu'au receipt meme en cas d'echec KX108) mais ne determine jamais l'autorite retournee

**Dette restante, honnetement signalee** :
- `KX108Client` HTTP reel non implemente (hors scope F5 — aucun Kernel accessible pour le developper contre une vraie cible ; l'interface est prete, l'implementation concrete est un travail futur quand un acces reel existera)
- Le bloc `evidence` de `ir_payload.py` est une extension du schema reel du core, non standardisee cote Kernel — si un vrai Kernel existe un jour et ignore ce bloc, aucune regression n'est attendue (additif, non consomme) ; s'il le rejette (schema strict), il faudra l'adapter
- Aucun test d'integration bout-en-bout avec un `CycleEngine` complet instancie (le style de test suit celui deja etabli en F3 : reproduction fidele de la double barriere via `_broker_gate`, pas d'instanciation du moteur complet — coherent avec `test_governance_boundary.py`)

**Statut F5 : DONE.**

**Prochain verrou concret avant F6 (Execution/Binder reel avec Alpaca)** : F6 doit cabler un `CycleEngine` complet avec `KX108GovernanceBridge` (actuellement injectable mais jamais instancie dans un moteur reel dans ce repo), le roster natif via `NativeRosterAnalysisAdapter` (F3), et le broker Alpaca paper (F2) — en tranchant explicitement quel `KX108Client` est utilise par defaut (probablement `UnavailableKX108Client` tant qu'aucun Kernel reel n'existe, ce qui rendrait le systeme complet fail-closed par construction jusqu'a branchement d'un vrai Kernel — a confirmer avec l'utilisateur avant de commencer F6, car cela signifie qu'aucune execution paper n'est possible tant que ce choix n'est pas fait consciemment).

## F6 — Execution/Binder avec Alpaca PAPER ONLY (2026-09-21)

```
Destination: native/agents/aggregation.py (NOUVEAU)
Source: aucune — code nouveau, inspire du pattern de agent-trad-main: obsidia/adapters/legacy_agents.py::LegacyAggregationAdapter (lu en reference, non copie car couple au vocabulaire AgentVote legacy)
Original path: N/A
Action: REWRITE_SMALL
Reason: aucune implementation d'AggregationPort n'existait pour le roster natif a 17 agents (celle d'agent-trad-main etait couplee a son roster a 14 agents, volontairement non retenu — cf. section F3 ci-dessus). Reduction pure AgentOutput.signal/confidence -> Consensus, aucune autorite.
Behavior changed: N/A (nouveau code)
Authority impact: NONE (agregation de votes, jamais une decision)
```

```
Destination: execution/binder/order_ledger_jsonl.py
Source: agent-trad-main
Original path: obsidia/adapters/jsonl_order_ledger.py
Action: COPY_AS_IS (imports reecrits obsidia.domain.* -> domain.*)
Reason: seule implementation disponible d'OrderLedgerPort ; pure persistance append-only avec garde anti-doublon (submission_blocker) — exactement le mecanisme d'idempotence demande par l'utilisateur (test #8), aucune logique de decision
Behavior changed: NO
Authority impact: NONE
```

```
Destination: execution/binder/paper_execution.py (NOUVEAU — point d'assemblage F6)
Source: aucune — code nouveau, assemble des pieces existantes (F2 Alpaca, F3 Binder/roster, F5 Governance Bridge)
Original path: N/A
Action: REWRITE_SMALL
Reason: aucun point d'assemblage production ne cablait encore Bridge -> Binder -> Alpaca. Ce module NE RECREE PAS le Runtime Binder central (il utilise execution/binder/engine.py tel quel) ; il ajoute uniquement `require_paper_mode` (refus structurel de Mode.LIVE, leve LiveModeRejected AVANT toute construction de broker) et `build_paper_cycle_engine` (factory). Le parametre `kx108_client` est obligatoire, sans valeur par defaut — impossible de charger un client par accident.
Behavior changed: N/A (nouveau code, aucune source ne faisait deja cet assemblage)
Authority impact: NONE (assemble des ports, ne decide rien lui-meme ; l'autorite reste exclusivement dans KX108GovernanceBridge)
```

```
Destination: tests/test_support/kx108_fixtures.py (NOUVEAU — namespace isole)
Source: aucune — code nouveau, en reaction explicite a la demande utilisateur de durcir l'isolation par rapport aux doubles de test deja presents dans governance/bridge/kx108_client.py (StaticKX108Client/RaisingKX108Client, F5, non deplaces — hors scope F6, restent utilisables par tests/unit/test_governance_bridge.py)
Original path: N/A
Action: REWRITE_SMALL
Reason: l'utilisateur exige qu'un client de test soit "impossible a confondre avec le vrai KX108" : nom explicite (FixtureKX108Client), docstring TEST-ONLY/NON-PRODUCTION, RuntimeWarning a l'instanciation, emplacement exclusivement sous tests/, aucune reference production nulle part (verifie par test_fixture_client_not_loadable_from_production_config)
Behavior changed: N/A (nouveau code, tests uniquement)
Authority impact: NONE (verdict fixe fourni par l'appelant du test, zero logique metier)
```

```
Destination: tests/integration/test_paper_execution_pipeline.py (NOUVEAU)
Source: aucune — 12 tests nouveaux
Original path: N/A
Action: REWRITE_SMALL
Reason: exercice du CycleEngine reel (F3) + KX108GovernanceBridge reel (F5) avec un broker Alpaca FAKE (spy, pas de reseau) et FixtureKX108Client (TEST-ONLY). Choix documente : l'analyse/strategie/dimensionnement sont des doubles deterministes plutot que le roster natif complet, pour isoler ce qui est teste ici (le cablage de gouvernance et d'execution) de ce qui l'est deja ailleurs (tests/unit/test_native_roster.py pour les agents, tests/unit/test_alpaca_providers.py pour le HTTP Alpaca)
Behavior changed: N/A (tests uniquement)
Authority impact: NONE
```

**Resultat des tests F6** : `pytest tests/ -q` -> **83 passed, 1 skipped** (71 precedents + 12 nouveaux, meme skip documente depuis F2, **aucune regression**).

**Chemin exact Bridge -> Binder -> Alpaca** :
`execution/binder/paper_execution.py::build_paper_cycle_engine` construit un `CycleEngine` (execution/binder/engine.py, F3) avec `authority=KX108GovernanceBridge(kx108_client)` (F5) et `broker=AlpacaBroker(...)` (F2, force `mode=config.mode` apres `require_paper_mode`). A l'interieur du cycle : `CycleEngine.run_cycle()` appelle `self.authority.evaluate(proposal, state, decision_id)` (Bridge, produit `Decision.authority`) -> `self._plan(decision, state, note)` (ExecutionPlanner, F3, premiere barriere : refuse si `not decision.authorizes_action`) -> `self._execute(cycle_id, decision, plan, note)` (deuxieme barriere : revalide `decision.authorizes_action` et `plan.is_authorized`, verifie `order_ledger.submission_blocker(plan)` pour l'idempotence, PUIS SEULEMENT `self.broker.submit(plan)`).

**Protections Binder (empechent un ACT du bridge de devenir une execution automatique)** :
1. `ExecutionPlanner.plan()` retourne `None` si l'autorite n'est pas ACT, si l'action n'est pas irreversible, si la quantite est nulle, ou si `state.can_support_irreversible_action(symbol)` est faux (compte bloque, marche ferme, prix invalide, qualite de donnee insuffisante)
2. `CycleEngine._execute()` revalide independamment `decision.authorizes_action and plan.is_authorized` avant tout appel broker — meme un plan mal construit ne passerait pas
3. `AlpacaBroker.submit()` leve lui-meme `UnauthorizedExecution` si `plan.is_authorized` est faux — troisieme verification independante, au plus pres du reseau

**Protections paper/live** :
- `require_paper_mode(config)` leve `LiveModeRejected` si `config.mode is not Mode.PAPER`, appele en tout premier dans `build_paper_cycle_engine` — AVANT la construction du `AlpacaHTTPClient`/`AlpacaBroker` : aucune connexion, meme en lecture, ne peut avoir lieu vers un compte live via ce point d'assemblage
- Aucun fallback : si la config est live ou ambigue (valeur `ALPACA_MODE` invalide), `AlpacaConfig.from_env()` (F2) leve deja `AlpacaConfigurationError` avant meme d'atteindre `require_paper_mode`
- Test dedie : `test_require_paper_mode_rejects_live_configuration`

**Tests — PASS/FAIL exact pour les 10 scenarios demandes** :
1. BLOCK -> aucune execution : PASS (`test_block_or_hold_verdict_never_reaches_broker[BLOCK]`)
2. HOLD -> aucune execution : PASS (`test_block_or_hold_verdict_never_reaches_broker[HOLD]`)
3. ACT + Binder refuse (etat degrade) -> aucune execution : PASS (`test_act_verdict_with_degraded_state_still_refuses_execution`)
4. ACT + Binder autorise -> ordre PAPER : PASS (`test_act_verdict_with_supported_state_submits_paper_order_only`)
5. Tentative LIVE -> refus : PASS (`test_require_paper_mode_rejects_live_configuration` + `test_require_paper_mode_accepts_paper_configuration` pour le cas positif)
6. Permission/compte invalide -> refus : PASS (`test_broker_permission_denied_blocks_before_submission`)
7. Erreur Alpaca a la soumission -> echec explicite, jamais faux succes : PASS (`test_alpaca_submission_error_produces_explicit_failure_never_false_success`)
8. Double soumission -> idempotence : PASS (`test_duplicate_execution_plan_is_blocked_by_order_ledger`)
9. Provenance KX108 conservee jusqu'au receipt : PASS (`test_kx108_verdict_provenance_survives_to_receipt`)
10. Aucun agent/simulation/adapter -> Alpaca directement : PASS (`test_no_direct_import_of_alpaca_outside_execution_assembly_point`)

Plus un 11e test explicitement demande : `test_fixture_client_not_loadable_from_production_config` — PASS.

**Receipts/resultats produits** : `CycleOutcome.receipt` (domain/receipt.py::CycleReceipt, deja existant depuis F2) est produit pour CHAQUE cycle quel que soit le verdict (ACT/HOLD/BLOCK), conformement a l'invariant deja garanti par `engine.py` (F3). `receipt.as_dict()["decision"]["metrics"]["kx108_response"]` porte la source exacte du verdict (`"FixtureKX108Client (TEST-ONLY)"` en test, `"KX108_BRIDGE"` en production reelle via le `reason` de la Decision). Structure suffisante pour F7 (le vrai receipt chaine SHA-256 existe deja, F6 ne fait qu'alimenter son contenu).

**Dette restante, honnetement signalee** :
- Aucun test d'integration n'exerce le vrai roster natif de 17 agents dans ce pipeline (choix deliberé, deja justifie ci-dessus) — un test complementaire natif-roster + paper Alpaca serait utile mais n'etait pas dans le perimetre strict F6 demande
- `NativeRosterAggregation` (nouveau) n'est pas exercee directement par les tests F6 (les tests utilisent `FakeAggregation`) — elle est neuve et non testee unitairement a ce stade ; a couvrir avant de la considerer prete pour une execution reelle
- `execution/binder/order_ledger_jsonl.py` est teste uniquement pour son role d'idempotence dans ce fichier (test #8) ; `verify_integrity()` et la detection de corruption ne sont pas exercees ici (deja testees implicitement par la source d'origine, non re-verifiees dans ce repo)
- Aucun `KX108Client` HTTP reel n'existe toujours (attendu, documente depuis F5)

**Statut F6 : DONE.**

**Prochain verrou concret avant F7 (Proof/Replay)** : le receipt actuel (`CycleReceipt`) est deja chaine (F2, `previous_receipt_hash`/`decision_hash()`) mais aucun mecanisme de PERSISTANCE durable de la chaine n'existe encore dans ce repo (le port `proof` de `CycleEngine` est optionnel et jamais implemente ici) — F7 doit decider ou et comment stocker durablement la chaine de receipts (fichier JSONL comme l'order ledger ? autre ?), et si le rejeu deterministe (`FrozenClock`/`FixedClock`, deja portes) doit etre exerce contre cette chaine stockee pour prouver qu'un rejeu produit exactement le meme hash.

## F7 - Proof/Replay (2026-09-21)

```
Destination: proof/receipts/{receipt_store,receipt_chain,receipt_verify,replay}.py
Source: domain/receipt.py (F3, reutilise) + conception nouvelle
Original path: N/A (nouveau code, s'appuie sur CycleReceipt/verify_chain existants)
Action: REWRITE_SMALL (persistance/verification/replay) + reutilisation explicite
        de CycleReceipt (pas de duplication, voir receipt_chain.py docstring)
Reason: F3 avait deja le chainage (GENESIS_HASH, decision_hash, previous_receipt_hash)
        mais aucune persistance durable ni mecanisme de replay
Behavior changed: NO pour domain/receipt.py (inchange) ; NOUVEAU comportement
        additif pour la persistance/verification/replay
Authority impact: NONE (verifie explicitement par
        tests/unit/test_receipt_chain.py::test_proof_is_not_authority et
        test_persisting_a_receipt_never_changes_its_decision, et
        test_replay_has_no_broker_or_binder_import)
```

```
Destination: execution/binder/paper_execution.py (parametre `proof` ajoute)
Source: modification additive du point d'assemblage F6
Original path: N/A
Action: ADAPT (une ligne de parametre + passage a CycleEngine(proof=...), retro-compatible :
        appels existants sans `proof=` gardent le comportement F6 exact, GENESIS_HASH en memoire)
Reason: brancher ReceiptStore sur le pipeline PAPER sans dupliquer l'assemblage
Behavior changed: NO par defaut (proof=None inchange) ; OUI si `proof=` est fourni
Authority impact: NONE
```

### Schema du receipt persiste

Format JSONL, une ligne = stored_hash (sha256) + receipt.as_dict() complet (deja defini en F3,
domain/receipt.py::CycleReceipt) : cycle_id, parent_cycle_id, receipt_schema_version, decision_id,
mode, state_fingerprint, decision (authority/authority_legacy/reason/structural_score/risk_score/
metrics dont kx108_response et local_signal/rules_evaluated/proposal complet avec agent_outputs
-> unknowns/contradictions/risk_flags/evidence_refs), previous_receipt_hash, execution_plan,
execution_result, consequence, degraded_reasons, extensions (dont, depuis F7, "f7_simulation" :
seed/params/engine_version/output_digest/n_steps pour le rejeu deterministe). stored_hash est
calcule a l'ecriture sur le meme sous-ensemble de champs que CycleReceipt.decision_hash(), rejoue
a la lecture par ReceiptChainVerifier - c'est ce qui detecte une alteration meme sur le DERNIER
receipt de la chaine (le chainage par previous_receipt_hash seul ne le detecterait pas s'il n'y a
pas de receipt suivant).

### Mecanisme de hash-chain

hash_n = H(hashable_subset(receipt_n)), receipt_{n+1}.previous_receipt_hash = hash_n. Genese :
GENESIS_HASH = "0"*64 (deja definie en F3, reutilisee telle quelle). ReceiptChainVerifier.verify_lines
parcourt la chaine en O(n) et retourne un IntegrityReport(status=EMPTY|VALID|CORRUPTED, first_error,
first_error_index) - jamais de reparation silencieuse. Detecte : alteration de contenu (recalcul
de hash != stored_hash), suppression/reordonnancement (rupture previous_hash), cycle_id duplique,
JSON malforme (erreur explicite a la lecture), version de schema inconnue (refus explicite plutot
que tentative d'interpretation).

### Mecanisme de persistance

Append-only JSONL. Ecriture atomique par flush() + os.fsync(handle.fileno()) immediatement apres
chaque ligne (alternative ecartee : reecriture complete via fichier temporaire + rename a chaque
append, incompatible avec l'append-only demande). Aucune reecriture en place : record() leve
DuplicateCycleError sur un cycle_id deja present plutot que d'ecraser une ligne existante.

### Mecanisme de replay (2 niveaux)

- ReplayEngine.replay_audit(cycle_id) : reconstruction pure lecture (observed/proposed/
  kx108_verdict/binder_decision/execution) depuis un receipt stocke, zero effet de bord.
- ReplayEngine.replay_deterministic(cycle_id) : si extensions["f7_simulation"] est present,
  reconstruit simulation.trading_world.market_process.TradingParams depuis les parametres
  stockes et rejoue run_trading_simulation (F4, deterministe via Mulberry32(seed)), compare le
  digest du resultat au digest original -> MATCH/DIVERGENCE/NOT_REPLAYABLE (cas normal si le
  pipeline F6 actuel n'a pas branche simulation/ dans le cycle, voir dette ci-dessous).

### Tests - PASS/FAIL exact des 18 scenarios demandes + suite complete

tests/unit/test_receipt_chain.py (12 tests, scenarios 1-9 + 3 tests de frontiere) : 12/12 PASS.
tests/integration/test_replay.py (12 tests, scenarios 10-18 + variantes) : 12/12 PASS.
pytest tests/ -q (suite complete) : 107 passed, 1 skipped - zero regression sur les 83 passed/1
skipped acquis a la fin de F6.

Tests d'alteration realises : modification d'un ancien receipt (detectee via stored_hash),
suppression d'un receipt intermediaire (rupture de chaine detectee), mauvais previous_hash
(detecte), JSON malforme (erreur explicite), cycle_id duplique (refuse a l'ecriture par
DuplicateCycleError, et detecte a la lecture si present malgre tout dans le fichier).

Comportement sur restart : une nouvelle instance de ReceiptStore pointant sur le meme fichier
reprend last_hash() correctement (test_restart_resumes_chain_head_correctly) et peut continuer a
chainer de nouveaux receipts sans rupture.

Comportement sur receipt corrompu : ReceiptChainVerifier retourne IntegrityStatus.CORRUPTED avec
first_error et first_error_index explicites - jamais de correction silencieuse, jamais de crash
non gere (JSON malforme -> CorruptedReceiptLogError capturee et transformee en rapport explicite).

### Lien ledger (F6) et receipts (F7)

Non fusionnes, comme demande. execution/binder/order_ledger_jsonl.py (F6) reste responsable de
l'idempotence des ordres ; proof/receipts/ (F7) reste responsable de la preuve complete du cycle
decisionnel. Ils se referencent via decision_id/execution_plan_id presents dans les deux
journaux, sans dependance de code de l'un vers l'autre. JsonlOrderLedger.verify_integrity()
(ecrite en F6 mais jamais exercee, dette signalee a l'epoque) est desormais testee explicitement
par test_order_ledger_verify_integrity_is_exercised (scenario 18).

### Politique de preuve - PROOF_REQUIRED vs PROOF_BEST_EFFORT

Constat factuel sur le comportement ACTUEL de execution/binder/engine.py::_prove (F3, code
inchange par F7) : le bloc `if self.proof is not None: try: receipt = self.proof.record(receipt)
or receipt except Exception as exc: note(f"echec d'ecriture de la preuve: {exc}")` implemente
PROOF_BEST_EFFORT - si ReceiptStore.record() echoue, le cycle continue et pretend avoir reussi
cote decision/execution, seule une note de log signale l'echec de preuve. Pour le chemin
gouverne critique, la politique cible documentee ici est PROOF_REQUIRED : un echec de
persistance de la preuve devrait empecher le cycle de se presenter comme reussi. Conformement a
la consigne F7, ce changement de comportement global n'est PAS applique maintenant (il
modifierait engine.py, deja teste et fige depuis F3, sans revue separee dediee) - seul le
mecanisme (ReceiptStore, exceptions typees DuplicateCycleError/CorruptedReceiptLogError) est pret
a etre branche en mode PROOF_REQUIRED par un futur appelant qui choisirait de ne pas avaler
l'exception.

### Dette restante (honnetement signalee)

- StoredCycleReceipt (lecture) n'est PAS une reconstruction complete de CycleReceipt en objets
  vivants (Decision/ActionProposal/ExecutionPlan/ExecutionResult imbriques) : c'est un modele de
  lecture leger qui conserve le dictionnaire brut complet (rien n'est perdu pour l'audit) mais
  n'expose pas les memes methodes de comportement que l'objet d'origine. Reconstruire six
  dataclasses imbriquees depuis un JSON generique etait hors budget de temps de F7.
- Le replay deterministe ne peut s'exercer que sur des receipts portant deja une extension
  f7_simulation - le pipeline F6 actuel (paper_execution.py::build_paper_cycle_engine) ne branche
  pas encore simulation/ dans le cycle reel (F4 et F6 sont restes deux couches independantes
  jusqu'ici). Les tests de replay deterministe attachent donc l'extension manuellement pour
  prouver le MECANISME ; le cablage simulation -> cycle -> receipt reste a faire si un futur
  usage l'exige (probablement F8/F9, hors perimetre F7).
- Ecriture atomique par flush+fsync reduit mais n'elimine pas totalement, sur tous les systemes
  de fichiers, le risque theorique d'une ligne partiellement ecrite en cas de crash exactement
  pendant l'appel write() - alternative (fichier temporaire + rename par ligne) ecartee car
  incompatible avec l'append-only demande.

**Statut F1->F7 : DONE.**

**Confirmation explicite demandee** :
- Proof != Authority : prouve par test_proof_is_not_authority (aucune methode de
  receipt_store.py/receipt_verify.py ne cree ni ne retourne d'Authority/Decision).
- Replay != Execution : prouve par test_replay_has_no_broker_or_binder_import (aucun import
  market.adapters.*/execution.binder.paper_execution dans replay.py) et
  test_replay_never_calls_broker (le compteur d'appels du broker ne bouge pas pendant un replay).
- Receipt != Decision : prouve par test_persisting_a_receipt_never_changes_its_decision
  (outcome.decision.authority reste identique avant/apres persistance et relecture).

**Prochain verrou concret avant F8 (External Stack Adapter)** : F8 doit construire la couche de
normalisation generique qu'aucune generation historique ne fournit (confirme par l'audit,
TRADING_MIGRATION_MATRIX.md). Avant de la coder, il faut decider ce que "provenance externe"
signifie concretement pour le contrat canonique deja construit en F3.5 (domain/contracts/
canonical.py) : un AgentOutput produit par une stack externe doit-il porter un champ de
provenance distinct (ex: source_system) pour que le receipt puisse toujours repondre "cette
observation venait du domaine natif ou d'un adapter externe", ou le contrat actuel suffit-il tel
quel ? C'est une decision de conception a trancher avant d'ecrire external/normalization/, pas
pendant. **-> traite en F7.5 ci-dessous.**

## F7.5 — Source Provenance Closure (2026-09-21)

```
Destination: domain/provenance.py (NOUVEAU)
Source: aucune - code nouveau, structure imposee par l'utilisateur
Original path: N/A
Action: REWRITE_SMALL
Reason: SourceProvenance (source_system/source_kind/source_id/adapter_id/organization_id/
  original_event_id/observed_at/ingested_at) - structure extensible pour tracer natif/
  externe/humain/replay/simulation, distincte de domain.types.Provenance (fraicheur donnee
  marche, pas origine du signal). Regle centrale documentee et testee : la provenance ne
  donne AUCUNE autorite, ni superieure ni inferieure.
Behavior changed: NO (nouveau module, rien d'existant ne l'appelait avant cette phase)
Authority impact: NONE
```

```
Destination: domain/proposal.py::AgentOutput.source_provenance (champ ajoute)
Source: extension du type existant (F3.5)
Original path: domain/proposal.py
Action: ADAPT (champ Optional[SourceProvenance] = None ajoute en fin de dataclass -
  compatible avec tous les appels historiques F3-F7, aucun test existant modifie)
Reason: faire porter la provenance d'origine par le type qui traverse deja tout le pipeline
  (Source -> AgentOutput -> ActionProposal -> Decision -> CycleReceipt) sans creer de second
  chemin de transport parallele.
Behavior changed: NO (champ optionnel, defaut None, serialise dans as_dict())
Authority impact: NONE
```

```
Destination: domain/contracts/canonical.py::to_canonical_agent_signal (parametre ajoute)
Source: extension du point de convergence F3.5
Original path: domain/contracts/canonical.py
Action: ADAPT (parametre source_provenance optionnel ajoute, table de correspondance mise a
  jour pour distinguer Provenance/fraicheur de SourceProvenance/origine)
Reason: le point de convergence unique doit pouvoir transporter la provenance pour TOUT futur
  producteur (natif ou externe F8), sans dupliquer la logique de construction.
Behavior changed: NO
Authority impact: NONE
```

```
Destination: native/agents/adapter.py::agent_vote_to_agent_output
Source: adapter existant (F3)
Original path: native/agents/adapter.py
Action: ADAPT (source_provenance=SourceProvenance.for_native_agent(vote.agent_id) attache
  automatiquement - SEUL endroit qui tague un signal comme natif, pas de valeur par defaut
  dispersee ailleurs)
Reason: compatibilite totale avec l'historique (tous les appels existants continuent de
  fonctionner) tout en garantissant qu'aucun signal natif ne traverse desormais sans
  provenance explicite.
Behavior changed: NO (les 107 tests F1-F7 restent verts sans modification)
Authority impact: NONE
```

```
Destination: tests/unit/test_source_provenance.py (NOUVEAU, 13 tests)
Source: cahier des charges utilisateur (10 tests obligatoires + 3 variantes parametrees)
Original path: N/A
Action: REWRITE_SMALL
Reason: preuve des 10 scenarios demandes (native survit, externe survit, human jamais
  converti, source_id+adapter_id conserves ensemble, replay preserve l'original ET
  for_replay_of distingue une regeneration, absence = None jamais devine, provenance ne
  change jamais Decision.authority (parametre sur ACT/HOLD/BLOCK), pas d'acces
  Binder/Broker depuis domain/provenance.py, roundtrip JSONL bit a bit, schema_version
  inchange + ancien format sans la cle relu sans erreur).
Behavior changed: N/A (tests)
Authority impact: NONE
```

**Choix de conception documente : PAS de bump de `RECEIPT_SCHEMA_VERSION`.** L'ajout de
`source_provenance` est purement additif (champ optionnel, defaut `None`). Un receipt ecrit
avant F7.5 (sans cette cle dans ses `agent_outputs`) reste lisible sans erreur
(`dict.get("source_provenance")` renvoie `None` naturellement) - verifie explicitement par
`test_receipt_schema_version_unchanged_and_old_format_still_readable`. `receipt_verify.py`
continue de refuser toute version differente de `receipt.v1` (aucun assouplissement de cette
regle F7).

**Integration au Governance Bridge (F5) : AUCUNE modification necessaire.**
`KX108GovernanceBridge.evaluate()` transmet `proposal` (donc `agent_outputs`, donc leur
`source_provenance`) sans jamais le lire - la structure existante depuis F5 satisfaisait deja
la regle "le Bridge ne doit jamais modifier silencieusement la provenance", simplement parce
qu'il ne l'inspecte pas. Confirme par `test_source_provenance_never_changes_decision_authority`
(parametre sur ACT/HOLD/BLOCK) : deux `AgentOutput` identiques sauf la provenance produisent
exactement la meme `Authority`.

**Replay (F7) : `replay_audit` preserve deja la provenance originale sans modification**, car il
ne fait que recopier le dict brut stocke (`AuditReplayResult.proposed["agent_outputs"]`).
`SourceProvenance.for_replay_of()` est fourni et teste unitairement, mais **n'est PAS branche
dans `proof/receipts/replay.py`** - `replay_deterministic` ne regenere jamais d'`AgentOutput`,
seulement une trajectoire de simulation (digest compare). Ce constructeur reste un point
d'extension documente pour un futur mecanisme qui rejouerait activement des agents (dette
consciente, pas un oubli).

**Tests** : `pytest tests/ -q` -> **120 passed, 1 skipped** (13 nouveaux, zero regression sur
les 107 precedents).

**Dette restante** : aucun mecanisme technique n'empeche encore de construire un `AgentOutput`
avec un `source_provenance` incoherent a la main (ex: `source_system=NATIVE` sur un signal en
realite externe) - c'est une convention type-safe (enums `SourceSystem`/`SourceKind`) mais pas
une garantie cryptographique. A renforcer si necessaire quand l'adapter externe (F8) devient le
seul point d'entree reel pour des signaux tiers.

**Statut F7.5 : DONE.** `pytest tests/ -q` integralement vert -> enchainement sur F8 autorise
par la consigne utilisateur ("si et SEULEMENT SI... enchaine directement sur F8").

## F8 — External Stack Adapter (2026-09-21)

```
Destination: external/contracts/external_signal.py (NOUVEAU)
Source: aucune - code nouveau
Original path: N/A
Action: REWRITE_SMALL
Reason: ExternalSignal - format d'entree generique et volontairement pauvre qu'une stack
  tierce doit fournir (source_id/organization_id/signal/confidence/rationale obligatoires,
  unknowns/contradictions/risk_flags/evidence_refs optionnels). `from_raw_payload` est
  l'etape VALIDATION du diagramme F8 : rejette (InvalidExternalSignal) tout champ
  obligatoire manquant/vide/mal type, sans jamais deviner une valeur.
Behavior changed: NO (nouveau module)
Authority impact: NONE
```

```
Destination: external/normalization/normalizer.py (NOUVEAU)
Source: reutilise domain/contracts/canonical.py::to_canonical_agent_signal (F3.5/F7.5)
Original path: N/A
Action: REWRITE_SMALL
Reason: traduit ExternalSignal -> CanonicalAgentSignal via le MEME point de convergence
  que le chemin natif (native/agents/adapter.py) - aucun second chemin de gouvernance.
  Preserve la provenance (source_system=external TOUJOURS, jamais reecrit) et les
  unknowns/contradictions/risk_flags sans inference : absents du signal externe, ils
  restent des tuples vides (documente comme "non rapporte", pas "verifie absent").
Behavior changed: NO
Authority impact: NONE - ne vote pas, ne decide jamais, aucun import governance.bridge
```

```
Destination: external/adapters/base_adapter.py (NOUVEAU)
Source: calque sur native/agents/adapter.py::NativeRosterAnalysisAdapter (F3)
Original path: N/A
Action: REWRITE_SMALL
Reason: `ExternalStackAdapter` (Protocol, point d'extension pour une future integration
  reelle) + `ExternalStackAnalysisAdapter` (implemente AnalysisPort exactement comme le
  roster natif - branchable dans CycleEngine sans AUCUNE modification du moteur, du
  Governance Bridge ou de KX108). C'est la preuve structurelle qu'aucune deuxieme
  architecture metier n'est creee.
Behavior changed: NO
Authority impact: NONE - aucun import execution.binder ni market.adapters.alpaca
```

```
Destination: external/examples/brother_stack/example_adapter.py (NOUVEAU)
Source: fixture pedagogique, aucune vraie integration
Original path: N/A
Action: KEEP_REFERENCE_ONLY (explicitement marque comme exemple, pas une integration reelle
  du projet du frere de l'utilisateur - conforme a la demande initiale "pas besoin
  d'integrer reellement le projet de mon frere maintenant")
Reason: demontrer la forme attendue d'un adapter concret sans dependance reseau/donnee reelle
Behavior changed: N/A
Authority impact: NONE
```

```
Destination: tests/unit/test_external_adapter.py (NOUVEAU, 12 tests)
Source: cahier des charges utilisateur (7 tests obligatoires + 5 variantes de robustesse)
Original path: N/A
Action: REWRITE_SMALL
Reason: preuve des 7 scenarios demandes (signal valide normalise avec provenance externe,
  champs manquants rejetes explicitement (parametre sur les 5 champs obligatoires +
  confidence non-numerique), meme Governance Bridge produit la meme forme de Decision pour
  natif et externe, aucun import Binder/Broker dans external/, normalizer n'importe jamais
  governance.bridge, unknowns/contradictions/risk_flags survivent, organization_id+
  adapter_id+source_id tous conserves bout-en-bout jusqu'au receipt).
Behavior changed: N/A (tests)
Authority impact: NONE
```

**Regles non negociables verifiees par test (pas seulement documentees)** :
- Adapter != Agent Authority : le normalizer traduit, ne vote jamais lui-meme (aucune
  logique de decision dans normalize_external_signal, juste une transcription 1:1 des
  champs du signal externe).
- Adapter != Governance : `test_normalizer_and_adapters_never_import_governance_bridge`
  (aucun import `governance.bridge` dans `external/contracts/`, `external/normalization/`,
  `external/adapters/`).
- Adapter != KX108 : ne produit jamais de verdict Authority - seul `to_canonical_agent_signal`
  produit un `AgentOutput` (signal), jamais une `Decision`.
- Adapter != Binder / Execution : `test_external_package_has_no_binder_or_broker_import`
  (scan ligne par ligne des vrais imports, pas des mentions en docstring, dans tout `external/`).

**Meme chemin de gouvernance, pas de duplication** : `test_normalized_external_signal_
produces_decision_via_same_bridge_as_native` instancie UN SEUL `KX108GovernanceBridge` et lui
soumet successivement un signal natif et un signal externe normalise - meme type de retour,
meme `Authority` pour la meme confiance/verdict KX108. Aucune branche de code specifique a
"external" n'existe dans la gouvernance elle-meme.

**Tests** : `pytest tests/ -q` -> **132 passed, 1 skipped** (12 nouveaux, zero regression sur
les 120 precedents).

**Dette restante** :
1. `unknowns`/`contradictions`/`risk_flags` absents d'un `ExternalSignal` restent des tuples
   vides - ambiguite documentee (non-rapporte vs verifie-absent) mais non resolue au niveau
   du type (pas de marqueur "non fourni" distinct de "liste vide"). Meme limite deja notee en
   F7.5 pour la coherence generale de `source_provenance`.
2. `ExternalStackAdapter` (Protocol) n'a aucune garantie technique empechant un futur adapter
   concret d'appeler un service externe avec des effets de bord depuis `fetch_signals` (ex:
   modifier un etat cote stack tierce) - la doctrine "observe seulement" est une convention
   documentee, pas verifiee par le type system.
3. Aucune vraie integration (brother_stack ou entreprise) n'existe : `ExampleBrotherStackAdapter`
   est explicitement une fixture, pas un branchement reel.

**Statut F1->F8 : DONE.**

**Prochain verrou concret avant F9 (Demo/Cockpit)** : F4 (simulation) et F8 (external adapter)
restent tous deux non cables dans le pipeline `CycleEngine` reel en meme temps que F6/F7 -
`ExternalStackAnalysisAdapter` a ete verifie isolement (tests unitaires) mais aucun scenario
n'exerce encore "signal externe -> Governance Bridge -> Binder -> Alpaca paper -> Receipt avec
extension f7_simulation" en un seul cycle bout-en-bout. Avant F9 (qui doit pouvoir montrer un
Cockpit demo), il faut decider si ce cablage integral complet est un prerequis demonstratif ou
si F9 peut se contenter d'assembler les pieces deja prouvees separement (F2 Alpaca, F4
simulation, F6 execution, F7 proof, F7.5 provenance, F8 external) sans un test d'integration
unique qui les exerce toutes ensemble. **-> traite en F8.5 ci-dessous.**

## F8.5 — Full End-to-End Integration (2026-09-21)

**Aucune nouvelle brique metier.** Ce chantier assemble uniquement des pieces
deja construites et prouvees separement (F2/F3/F3.5/F4/F5/F6/F7/F7.5/F8) dans
UN test d'integration qui les fait toutes traverser reellement en un seul
cycle. Le seul "cablage" ajoute est une fonction utilitaire de test
(`_attach_simulation_evidence`) qui execute reellement `run_trading_simulation`
(F4) et attache son resultat sur `receipt.extensions["f7_simulation"]` AVANT
persistance — `execution/binder/engine.py` (fige depuis F3/F5) n'est PAS
modifie : `CycleReceipt.extensions` est un dict mutable a l'interieur d'un
dataclass frozen, muter son contenu avant `store.record()` est le mecanisme
documente par F7 pour un enrichissement pre-persistance (meme principe que le
decorateur de preuve mentionne dans `engine.py::_prove`).

```
Destination: tests/integration/test_end_to_end_full_stack.py (NOUVEAU, 11 tests)
Source: assemblage de composants deja portes (aucune nouvelle source)
Original path: N/A
Action: REWRITE_SMALL (tests uniquement)
Reason: preuve d'assemblage des 7 scenarios contraints + hash-chain globale +
  alteration volontaire + tests structurels groupes demandes par l'utilisateur
Behavior changed: N/A (aucun fichier de production modifie)
Authority impact: NONE
```

**Deux chemins obligatoires, memes composants apres convergence** :
- NATIF : `NativeRosterAnalysisAdapter()` (F3, vrai roster de 17 agents, pas
  un double) — utilise directement dans les scenarios 1 et 7, produit 17
  `AgentOutput` tagues `source_provenance.source_system=native` (F7.5).
- EXTERNE : `ExternalStackAnalysisAdapter(ExampleBrotherStackAdapter())` (F8)
  — meme `KX108GovernanceBridge`, meme `CycleEngine`, meme `AlpacaBroker` fake.
  `test_scenario_7_...` prouve `type(decision_native) is type(decision_external)`
  et que les DEUX passent par le meme point d'assemblage sans branche de code
  dediee a "external" dans la gouvernance.

**Constat honnete (dette decouverte, non corrigee ici — hors scope F8.5)** :
`native/agents/adapter.py::agent_vote_to_agent_output` construit `AgentOutput`
directement (memes champs), SANS appeler litteralement
`domain.contracts.canonical.to_canonical_agent_signal` — seul
`external/normalization/normalizer.py` (F8) utilise ce point de convergence
pour de vrai. Les deux chemins produisent la MEME FORME de sortie (verifie
par les tests), mais le "point de convergence unique" documente en F3.5 n'est
aujourd'hui emprunte que par le chemin externe. Corriger cela serait modifier
`native/agents/adapter.py`, une brique de production deja figee et testee —
explicitement hors perimetre F8.5 ("pas de nouvelle brique metier"). Signale
pour une future revue, pas corrige silencieusement.

**Les 7 scenarios contraints, tous reellement executes** :
1. ACT + simulation reelle attachee -> 1 ordre PAPER, 1 receipt persiste, hash
   valide, replay audit PASS, replay deterministe MATCH (meme seed) puis
   digest different confirme sur une seed differente (PASS)
2. HOLD -> aucun ordre, receipt produit, replay audit retrouve `authority=HOLD`
3. BLOCK -> aucune execution, raison + source KX108 tracables dans le receipt
4. ACT + Binder refuse (compte bloque) -> aucun ordre ; prouve Decision != Permission
5. Erreur broker -> `execution.submitted=False`, `consequence.executed=False`,
   jamais un faux succes
6. Double soumission du meme `ExecutionPlan`/`client_order_id` -> premiere
   acceptee, seconde rejetee ("idempotence"), broker appele une seule fois
   (reutilise `execution/binder/order_ledger_jsonl.py`, F6, sans modification)
7. Provenance native vs externe -> les DEUX receipts, RECHARGES DEPUIS LE
   STORE (`store.find_by_cycle_id`, pas depuis la memoire), portent
   `source_provenance` intact (source_system/source_id/adapter_id/
   organization_id) ; les `unknowns`/`risk_flags` de la stack externe
   (`ExampleBrotherStackAdapter`, F8) survivent jusqu'au receipt relu

**Hash-chain globale** (`test_full_chain_across_all_scenarios_is_valid_then_detects_tampering`) :
4 cycles (HOLD, BLOCK, ACT-degrade, ACT) chaines dans UN seul fichier ->
`IntegrityStatus.VALID`, `checked_count=4`. Alteration d'un receipt
intermediaire sur une COPIE (`shutil.copy`, jamais l'original) -> `CORRUPTED`,
`first_error_index=1`. L'original reste `VALID` apres coup : aucune
contamination, aucune reparation automatique.

**Tests structurels groupes** (`test_no_category_ever_grants_itself_authority_beyond_its_role`) :
Agent != Authority, External Adapter != Authority, Simulation != Authority
(le resultat de simulation n'entre jamais dans `Decision`, seulement dans
`extensions`), Intent != Action, KX108 Decision != Binder Permission, Binder
Permission != Execution Success, Receipt != Decision, Proof != Authority,
Replay != Execution, Source Provenance != Trust (un signal externe et un
signal natif produisent la meme `Authority` pour le meme verdict KX108 —
ni bonus ni malus de confiance lie a la provenance) — toutes verifiees
ENSEMBLE sur des cycles reels partageant le meme store, pas seulement
rappelees isolement depuis F3-F8.

**Resultat des tests** : `pytest tests/integration/test_end_to_end_full_stack.py -q`
-> 11/11 PASS. `pytest tests/ -q` (suite complete) -> **143 passed, 1 skipped**
(11 nouveaux, zero regression sur les 132 precedents).

**Dette restante, honnetement signalee** :
1. Le "point de convergence unique" (`to_canonical_agent_signal`) n'est
   emprunte que par le chemin externe (F8), pas par le chemin natif (F3) —
   voir constat ci-dessus, non corrige (hors scope).
2. Le cablage simulation -> cycle reel reste une fonction de TEST
   (`_attach_simulation_evidence`), pas un mecanisme de production dans
   `execution/binder/paper_execution.py` — un futur appelant de production
   qui voudrait attacher systematiquement une simulation a chaque cycle ACT
   devrait le faire explicitement (ce chantier prouve que c'est possible et
   sans effet de bord, il ne l'automatise pas).
3. `NativeRosterAnalysisAdapter` est exerce ici sur des bars synthetiques
   deterministes (pas aleatoires, mais pas des donnees de marche reelles) —
   suffisant pour prouver l'assemblage architectural, pas une validation de
   la pertinence des signaux produits (deja hors scope, couverte separement
   par `tests/unit/test_native_roster.py`).

**Statut F1->F8.5 : DONE.**

**REPONSE EXPLICITE A LA QUESTION POSEE** : *"Est-ce qu'un seul cycle reel
traverse maintenant toute la stack F2 + F4 + F5 + F6 + F7 + F7.5 + F8 sans
rupture architecturale ?"*

**OUI**, avec une nuance honnete a connaitre : le scenario 1
(`test_scenario_1_act_with_simulation_produces_paper_order_and_replayable_receipt`)
fait reellement traverser un seul cycle par F2 (Alpaca fake, meme forme
d'objets que le vrai broker), F3 (roster natif reel + Binder reel), F4
(simulation reellement executee et son digest compare en replay), F5
(Governance Bridge reel + KX108 fixture), F6 (execution PAPER + ledger reel),
F7 (ReceiptStore + ReceiptChainVerifier + ReplayEngine reels), F7.5
(SourceProvenance native reelle sur les 17 sorties d'agents) — sans aucune
rupture, sans aucun mock d'une des couches de gouvernance elles-memes (seuls
le broker HTTP et les donnees de marche sont des fakes, deliberement, pour
eviter le reseau). F8 est prouve dans le meme test d'integration mais sur un
cycle SEPARE (scenario 7) plutot que dans le MEME cycle que la simulation F4
— rien n'empeche techniquement de les combiner (meme `AnalysisPort`,
meme moteur), ce n'etait simplement pas demande comme un seul et unique
cycle combinant les deux a la fois. La nuance documentee au point "constat
honnete" ci-dessus (convergence non empruntee par le chemin natif) est reelle
mais n'introduit aucune rupture architecturale observable par les tests :
les deux chemins produisent des `Decision` du meme type via le meme Bridge.

## F8.6 — External Full-Cycle Closure (2026-09-21)

```
Destination: tests/integration/test_end_to_end_external_full_stack.py (NOUVEAU)
Source: reutilisation stricte de F3/F4/F5/F6/F7/F7.5/F8 (aucun nouveau composant metier)
Original path: N/A
Action: REWRITE_SMALL (nouveau test, memes classes que test_end_to_end_full_stack.py de F8.5)
Reason: fermer la seule nuance laissee par F8.5 — le chemin EXTERNE n'avait jamais
    ete exerce dans le MEME cycle que la simulation F4 (F8.5 scenario 1 = natif
    seul ; F8.5 scenario 7 = externe seul, sans simulation attachee)
Behavior changed: NO (aucune brique de production modifiee, uniquement un test)
Authority impact: NONE
```

Deux scenarios obligatoires, chacun un cycle reel unique :

1. **EXTERNAL + ACT + simulation** (`test_scenario_1_external_act_with_simulation_produces_paper_order_and_replayable_receipt`) :
   `ExampleBrotherStackAdapter` (F8) -> `ExternalSignal` -> `ExternalStackAnalysisAdapter`
   -> `normalize_external_signal` -> `to_canonical_agent_signal` (MEME point de
   convergence que le natif, F3.5) -> `run_trading_simulation` (F4, reellement
   execute) -> attache comme Evidence (`receipt.extensions["f7_simulation"]`,
   jamais Authority) -> `KX108GovernanceBridge` (F5, `FixtureKX108Client` TEST-ONLY)
   -> `ExecutionPlanner`/`_execute` (F6) -> `FakeBroker` (spy, zero reseau)
   -> `CycleReceipt` -> `ReceiptStore.record` (F7) -> reload depuis le store
   (source_system=external, source_id="brother_strategy_07",
   adapter_id="brother_stack_v1", organization_id="brother_company",
   unknowns/risk_flags de la stack externe — tous intacts apres reload)
   -> `ReceiptChainVerifier` (VALID) -> `ReplayEngine.replay_audit` (zero appel
   broker supplementaire) -> `ReplayEngine.replay_deterministic` (meme seed ->
   MATCH). Exactement 1 appel `broker.submit`.

2. **EXTERNAL + BLOCK** (`test_scenario_2_external_block_no_execution_but_evidence_and_provenance_traceable`) :
   meme chemin jusqu'a KX108, fixture=BLOCK -> aucun appel broker, simulation/
   evidence quand meme attachee et persistee, provenance externe conservee,
   receipt BLOCK persiste avec raison tracable (`kx108_response.verdict == "BLOCK"`),
   replay audit fonctionnel (retrouve le cycle, `execution=None`, zero appel broker).

3. **Verifications structurelles** (`test_external_plus_simulation_context_preserves_all_boundaries`) :
   scan des lignes `import`/`from` reelles (pas des mentions en docstring) dans
   tout `external/` -> aucune vers `execution.binder`, `market.adapters.alpaca`
   ou `governance.bridge` (External Adapter != Binder/Execution/Governance) ;
   KX108=ACT + Binder degrade -> aucun ordre meme cote externe (Decision !=
   Permission, External Adapter != Authority) ; attacher une simulation ne
   change jamais `receipt.decision.authority` deja fige (Simulation !=
   Authority) ; verdict ACT identique quelle que soit la provenance
   native/externe (Source Provenance != Trust) ; persister/rejouer un receipt
   externe ne change jamais la Decision ni ne rappelle le broker (Receipt !=
   Decision, Replay != Execution).

**Aucun nouveau Bridge, Binder, type de receipt ou replay engine cree** — le
fichier reutilise `KX108GovernanceBridge`, `CycleEngine`/`ExecutionPlanner`,
`CycleReceipt`/`ReceiptStore`/`ReceiptChainVerifier`/`ReplayEngine`,
`ExternalStackAnalysisAdapter`/`ExampleBrotherStackAdapter` sans aucune
modification de leur code.

**Tests** : 3/3 PASS. Suite complete -> **146 passed, 1 skipped** (3 nouveaux,
zero regression sur les 143 precedents).

**Dette restante reelle avant F9** : la dette de convergence documentee en
F8.5 (`native/agents/adapter.py` n'emprunte pas litteralement
`to_canonical_agent_signal`, contrairement au chemin externe qui, lui, s'y
conforme strictement via `normalizer.py`) reste presente et n'a PAS ete
corrigee ici — F8.6 avait pour perimetre de prouver l'assemblage externe+
simulation, pas de retoucher le roster natif (interdiction explicite de
nouvelle architecture/composant). Cette dette est purement une difference de
chemin de code interne (les DEUX chemins produisent la meme forme
d'`AgentOutput` avec `source_provenance` correcte, verifie par tests) — elle
n'a jamais empeche aucune propriete de gouvernance de tenir, dans aucun des
scenarios F8.5 ou F8.6.

**REPONSE SANS NUANCE** : *"Un signal EXTERNE peut-il maintenant traverser
dans UN SEUL cycle toute la chaine F8 -> F4 -> F5 -> F6 -> F7/F7.5, jusqu'au
receipt et au replay, en utilisant exactement la meme gouvernance que le
natif ?"*

**OUI.**

F1 -> F8.6 = ARCHITECTURAL INTEGRATION CLOSED

## F8.7 — Canonical Convergence Closure (2026-09-21)

Objectif : fermer la derniere nuance documentee en F8.5/F8.6 — le chemin
Native construisait `AgentOutput(...)` directement dans
`native/agents/adapter.py::agent_vote_to_agent_output` au lieu d'emprunter
`domain.contracts.canonical.to_canonical_agent_signal`, le point de
convergence deja utilise par le chemin External depuis F8. Aucune nouvelle
fonctionnalite : uniquement un audit puis, si justifie, un refactor minimal.

### Audit (etape obligatoire avant toute modification)

`to_canonical_agent_signal` (`domain/contracts/canonical.py`) a ete relue
en entier. Sa signature est deja entierement neutre : `agent_id, category,
signal, confidence, rationale, unknowns, contradictions, risk_flags,
evidence_refs, operational_metadata, source_provenance` — aucun de ces
parametres ne presuppose un format `ExternalSignal` (pas de champ
`organization_id`/`adapter_id` bruts, pas de logique de validation
specifique a l'externe : cette logique reste dans
`external/contracts/external_signal.py` et
`external/normalization/normalizer.py`, en amont de l'appel).

**Verdict : CAS A — fonction deja reellement generique.** Aucun refactor de
`to_canonical_agent_signal` elle-meme n'etait necessaire ni souhaitable
(CAS B, extraction d'une primitive plus bas niveau, n'a pas eu lieu car il
n'y avait rien a extraire : la fonction existante EST deja la primitive
commune).

### Ancien chemin Native (avant F8.7)

```python
def agent_vote_to_agent_output(vote: AgentVote) -> AgentOutput:
    return AgentOutput(
        name=vote.agent_id,
        category=str(vote.domain),
        signal=vote.proposed_verdict,
        confidence=float(vote.confidence),
        rationale=vote.claim,
        unknowns=tuple(vote.unknowns),
        contradictions=tuple(vote.contradictions),
        risk_flags=tuple(vote.risk_flags),
        evidence_refs=tuple(vote.evidence_refs),
        source_provenance=SourceProvenance.for_native_agent(vote.agent_id),
        inputs_digest={
            "vote": vote.vote,
            "layer": vote.layer,
            "severity_hint": str(vote.severity_hint),
        },
    )
```

### Nouveau chemin Native (apres F8.7)

```python
def agent_vote_to_agent_output(vote: AgentVote) -> AgentOutput:
    return to_canonical_agent_signal(
        agent_id=vote.agent_id,
        category=str(vote.domain),
        signal=vote.proposed_verdict,
        confidence=float(vote.confidence),
        rationale=vote.claim,
        unknowns=vote.unknowns,
        contradictions=vote.contradictions,
        risk_flags=vote.risk_flags,
        evidence_refs=vote.evidence_refs,
        operational_metadata={
            "vote": vote.vote,
            "layer": vote.layer,
            "severity_hint": str(vote.severity_hint),
        },
        source_provenance=SourceProvenance.for_native_agent(vote.agent_id),
    )
```

Seul le point d'assemblage a change. `native/agents/domains/trading_agents.py`
(les 17 agents eux-memes, COPY_AS_IS depuis le core) n'a pas ete touche —
ils continuent de produire des `AgentVote`, sans savoir que ce vote finit
par passer par le meme builder que le chemin externe.

### Primitive canonique commune

`domain.contracts.canonical.to_canonical_agent_signal` — inchangee, deja
generique. Desormais appelee par LES DEUX chemins :
- `native/agents/adapter.py::agent_vote_to_agent_output`
- `external/normalization/normalizer.py::normalize_external_signal`

Aucune deuxieme implementation, aucun alias, aucune fonction miroir.

### Fichiers modifies

- `native/agents/adapter.py` — import ajoute
  (`from domain.contracts.canonical import to_canonical_agent_signal`),
  corps de `agent_vote_to_agent_output` remplace par un appel a cette
  fonction, docstring mise a jour pour documenter F8.7.
- `tests/unit/test_canonical_convergence.py` (nouveau, 11 tests).
- `docs/MIGRATION_PROVENANCE.md` (cette section).

Aucun changement a : `domain/contracts/canonical.py`,
`external/normalization/normalizer.py`, `governance/bridge/*`,
`execution/binder/*`, `market/adapters/alpaca/*`, `proof/receipts/*`,
`domain/receipt.py` (semantique du receipt intacte).

### Compatibilite

`ExternalStackAnalysisAdapter`/`normalize_external_signal` n'ont pas ete
touches — leur comportement est verifie inchangé par
`test_external_normalization_unchanged_after_native_refactor` et par la
suite `tests/unit/test_external_adapter.py` (12 tests, deja verte avant
F8.7, toujours verte apres). Les 17 agents natifs
(`native/agents/domains/trading_agents.py`) n'ont pas eu besoin d'etre
modifies : ils ignorent totalement l'existence de l'External Adapter, comme
exige. Aucun agent natif n'appelle ni ne connait
`ExternalStackAnalysisAdapter`, `ExternalSignal`, ou tout module sous
`external/`.

### Tests ajoutes (`tests/unit/test_canonical_convergence.py`, 11 tests)

1. `test_native_adapter_calls_the_same_canonical_builder_as_external` — PASS
2. `test_native_unknowns_survive_to_agent_output` — PASS
3. `test_native_contradictions_survive_to_agent_output` — PASS
4. `test_native_risk_flags_survive_to_agent_output` — PASS
5. `test_native_evidence_refs_survive_to_agent_output` — PASS
6. `test_native_source_provenance_survives_to_agent_output` — PASS
7. `test_external_normalization_unchanged_after_native_refactor` — PASS
8. `test_native_and_external_produce_the_same_canonical_type` — PASS
9. `test_provenance_alone_never_changes_decision_authority` — PASS
10. `test_native_roster_adapter_full_analyse_uses_canonical_builder_end_to_end`
    (cycle Native complet, 17 agents reels, remplace la duplication d'un
    scenario d'integration complet — les scenarios F8.5/F8.6 existants
    restent la preuve de reference pour le cycle complet et tournent
    inchanges dans la suite globale) — PASS
11. `test_only_the_canonical_builder_constructs_agent_output_directly`
    (garde-fou architectural : scan AST de tout le code source hors tests,
    verifie qu'aucun fichier autre que `domain/proposal.py` et
    `domain/contracts/canonical.py` ne construit `AgentOutput(...)`
    directement avec 4+ arguments nommes) — PASS

Item "cycle External complet toujours PASS" : verifie par la suite
existante `tests/integration/test_end_to_end_external_full_stack.py`
(F8.6), relancee telle quelle dans la suite globale, toujours verte.

### Suite totale

`pytest tests/ -q` -> **157 passed, 1 skipped** (146 + 11 nouveaux, zero
regression, le seul skip est celui documente depuis F2).

### Dette restante reelle avant F9

Aucune dette de convergence restante. La seule limite documentee est
generale et deja connue depuis les phases precedentes : le garde-fou
architectural (test 11) est une heuristique AST pragmatique (appel a
`AgentOutput(...)` avec >=4 kwargs), pas une garantie absolue — un
contournement deliberement adversarial (ex: `AgentOutput(**locals())`)
pourrait y echapper. Suffisant pour empecher une reconstruction
accidentelle d'une deuxieme logique de canonicalisation, pas pour se
proteger d'un code malveillant.

**REPONSE SANS NUANCE** : *"Existe-t-il maintenant UN SEUL mecanisme de
canonicalisation partage par Native et External avant la gouvernance ?"*

**OUI.**

F1 -> F8.7 = CANONICAL ARCHITECTURE CLOSED

## F9 — Cockpit/Demo (2026-09-21)

Objectif : rendre OBSERVABLE la stack F1->F8.7 deja prouvee. Aucune nouvelle
autorite, aucune nouvelle logique metier fondamentale. Le Cockpit est une
PROJECTION du runtime reel, pas un moteur parallele.

### Audit prealable (etape 0)
- `apps/{cockpit,demo,naive_vs_governed}/` (F1) etaient vides.
- Le clone `Obsidia-lab-trad/os4-platform/client/src/pages/TradingWorld.tsx`
  a servi d'INSPIRATION DE LAYOUT uniquement (sections Input/Domain
  State/Agents/Simulation/Intent/Governance/KX108/Binder/Execution/Receipt/
  Replay) -- aucun code React/tRPC importe.
- MVP-obsidia- (Streamlit, deja audite) a confirme que Streamlit est le seul
  pattern UI verifie fonctionnel dans la genealogie, coherent avec un repo
  100% Python -- **choix retenu** pour app.py. Rejete : reimporter le mode
  Guide/Expert du MVP tel quel (hors scope F9, pas demande).

### Fichiers crees
- `apps/__init__.py`, `apps/cockpit/__init__.py`
- `apps/cockpit/demo_doubles.py` -- doubles PAPER-only deterministes (memes
  formes que les doubles F8.5/F8.6, pas une nouvelle brique metier)
- `apps/cockpit/scenarios.py` -- catalogue des 7 scenarios executables +
  `replay_previous_cycle` (scenario 8), assemble uniquement des composants
  DEJA PROUVES (`CycleEngine` F3/F6, `KX108GovernanceBridge` F5,
  `NativeRosterAnalysisAdapter`/`ExternalStackAnalysisAdapter` F3.5/F8,
  `ExecutionPlanner` F6, `ReceiptStore`/`ReplayEngine` F7,
  `FixtureKX108Client` TEST-ONLY)
- `apps/cockpit/presenter.py` -- assemble les 11 sections d'affichage a
  partir de `CycleOutcome`/`ReceiptStore` reels, ne recalcule jamais un
  verdict/permission/resultat
- `apps/cockpit/app.py` -- rendu Streamlit fin, appelle uniquement
  scenarios.py/presenter.py
- `tests/unit/test_cockpit.py` (11 tests)
- `requirements.txt` (+`streamlit>=1.38.0`)

### Choix de conception notable : `_DeferredSimulationProof`
Proxy minimal du Protocol `ProofPort` (`last_hash`/`record`) dans
scenarios.py, permettant d'attacher la simulation F4 comme Evidence AVANT
persistance (meme contrainte que F8.5 scenario 1) SANS casser la continuite
de la chaine partagee entre scenarios successifs du Cockpit (contrairement a
F8.5 qui isolait chaque scenario dans son propre `tmp_path`). Ce n'est PAS un
nouveau mecanisme de preuve : `record()` est un no-op, la persistance reelle
reste `store.record(receipt)`, appele explicitement par `run_scenario`.

### Tests F9 (11/11 PASS)
1. Aucune assignation `Authority.ACT/HOLD/BLOCK` dans apps/cockpit/*.py (AST)
2. Vue affichee == `decision.authority` exact (pas de recalcul)
3. Aucun import direct `market.adapters.alpaca`/`execution.binder.paper_execution`
   dans apps/cockpit/*.py
4. BLOCK -> aucune execution declenchee par le Cockpit
5. Native et External produisent le meme type de `Decision` via le meme Bridge
6. Aucune construction `Mode.LIVE` dans le catalogue + `require_paper_mode` leve toujours
7. Replay (scenario 8) : `MATCH` reproductible, zero appel broker
8. Receipt affiche == receipt reellement persiste (hash/schema/raw identiques)
9. Erreur broker jamais affichee comme succes (`consequence.executed=False`)
10. Les 7 scenarios catalogues s'executent tous reellement sans crash
11. Scenario "ACT + Binder refuse" : Decision != Permission visible dans la vue

### Suite complete
`pytest tests/ -q` -> **168 passed, 1 skipped** (157 + 11, zero regression).

### Dette restante honnetement signalee
- app.py (rendu Streamlit) n'est pas teste automatiquement -- seule la
  couche donnees (scenarios.py/presenter.py) l'est, choix assume et documente.
- Le store du Cockpit est cree dans un dossier temporaire par session
  Streamlit (`tempfile.mkdtemp`) -- pas de persistance entre lancements de
  l'app, coherent avec "PAPER ONLY / demo", pas un choix de production.
- `_DeferredSimulationProof` est specifique au Cockpit (pas reutilise
  ailleurs) -- juge acceptable car il n'introduit aucune nouvelle semantique
  de preuve, seulement un sequencement different de persistance deja prouve.

### Statut F1->F9 : DONE.

### Prochain verrou avant F10 (Regression/Freeze)
Aucun test de non-regression historique multi-generations (MVP-obsidia-,
TradingWorld, ERC-8004, Obsidia-lab-trad) n'a encore ete rejoue contre le
nouveau moteur unifie -- F10 doit decider quel sous-ensemble de comportements
historiques merite un test de parite avant de figer une baseline, et si le
`merkle_seal.json` dedie a OBSIDIA_TRADING doit etre cree a ce stade ou
reporte.

## F10.1 — Historical Regression / Compatibility Audit (2026-09-21)

Matrice complete (39 proprietes) : `docs/F10_HISTORICAL_REGRESSION_MATRIX.md`.
39 proprietes auditees contre MVP-obsidia-, Obsidia-lab-trad/TradingWorld,
agent-trad-main, l'archive ERC-8004 et le roster actuel du core. 20 PRESERVED,
12 IMPROVED, 6 REPLACED_EQUIVALENTLY, 0 INTENTIONALLY_DROPPED, 1 MISSING
("Naive vs Governed", jamais implemente, `apps/naive_vs_governed/` vide),
2 NOT_PORTABLE (packs de tests formels du Kernel — hors perimetre ; matrice
de Markov non calibree — dette heritee documentee). `pytest tests/ -q` ->
168 passed, 1 skipped (zero regression par rapport a F9). REGRESSION=0
confirme independamment par le parent (deuxieme execution manuelle de
pytest, resultat identique).

### Statut F10.1 : DONE.

## F10.2 — Freeze (2026-09-21)

Fichiers crees :
- `docs/FREEZE_MANIFEST.json` + `docs/FREEZE_MANIFEST.md` (manifest machine
  et lisible)
- `docs/SEAL_SCOPE.md` (perimetre exact du merkle seal — voir ce document
  pour la liste complete de ce qui est/n'est pas scelle)
- `scripts/compute_seal.py` (algorithme reproductible : SHA-256 par fichier,
  puis SHA-256 de la liste triee (chemin, hash) -> root_hash)
- `merkle_seal.json` (racine du repo, **dedie a OBSIDIA_TRADING uniquement**
  — le merkle_seal.json du core Obsidia n'a pas ete touche)
- `tests/unit/test_freeze_manifest.py` (5 tests)

Perimetre scelle : 83 fichiers (code de production sous domain/, native/,
external/, market/, simulation/, governance/, execution/, proof/, apps/, plus
5 documents de gouvernance). tests/, __pycache__/, proof/receipts/data/,
.git/ explicitement exclus (voir docs/SEAL_SCOPE.md pour le detail complet).

Verifications faites avant generation du seal (pas supposees) :
- `receipt_schema_version` = "receipt.v1" (`domain/receipt.py`, inchange
  depuis F7).
- Proof policy toujours PROOF_BEST_EFFORT : `execution/binder/engine.py`,
  le bloc `try: receipt = self.proof.record(receipt) ... except Exception:
  note(...)` avale toujours l'echec d'ecriture sans interrompre le cycle —
  confirme par lecture directe, pas suppose.
- `native/agents/adapter.py` utilise bel et bien `to_canonical_agent_signal`
  depuis F8.7 — la dette "native != canonical builder" est donc **retiree**
  de la liste des dettes connues du freeze (elle etait deja resolue, ne pas
  la recopier par erreur).
- `apps/naive_vs_governed/` confirme toujours vide (`ls` direct).
- Matrice de Markov confirmee non calibree (docstring `market_process.py`
  lignes 19-21 et 65, lu directement).

`pytest tests/ -q` -> **173 passed, 1 skipped** (168 + 5 nouveaux tests de
freeze, zero regression).

### Statut F10.2 : DONE.

```
F1 -> F10 = DONE

ARCHITECTURE: CLOSED
CANONICAL CONVERGENCE: CLOSED
NATIVE PATH: PASS
EXTERNAL PATH: PASS
PAPER EXECUTION: PASS
PROOF / REPLAY: PASS
HISTORICAL REGRESSION: PASS
KNOWN REGRESSIONS: 0
FREEZE: SEALED
```

## DEMO — Naive vs Governed (branche demo/naive-vs-governed-v1)

> Post-freeze. Branche locale créée depuis le commit F10 gelé `9e68391` (préservé, vérifié intact). Ferme uniquement la dette F10 "Naive vs Governed demo missing" — aucune autre dette F10 n'est traitée ici.

### Fichiers créés/modifiés
- `apps/naive_vs_governed/__init__.py` (nouveau)
- `apps/naive_vs_governed/naive_path.py` (nouveau) — chemin Naive isolé
- `apps/naive_vs_governed/comparison.py` (nouveau) — assemble Naive + réutilise le runtime Governed existant
- `apps/cockpit/naive_vs_governed_view.py` (nouveau) — rendu Streamlit fin
- `apps/cockpit/app.py` (modifié) — ajout d'un sélecteur de vue sidebar ("Cockpit" / "Naive vs Governed"), aucune logique de gouvernance touchée
- `tests/unit/test_naive_vs_governed.py` (nouveau) — 12 tests

### Interdictions respectées (diff vide confirmé contre le commit F10 gelé `9e68391`)
`domain/contracts/canonical.py`, `governance/`, `execution/binder/`, `proof/receipts/`, `domain/provenance.py`, `docs/FREEZE_MANIFEST.{json,md}`, `merkle_seal.json` — **aucun n'a été modifié**.

### Architecture Naive — isolation
`apps/naive_vs_governed/naive_path.py` importe uniquement `domain.market` (types de données), `native.agents.contracts` (TradingState/AgentVote) et `native.agents.domains.trading_agents` (les 17 classes d'agents, directement — jamais via `native/agents/adapter.py`, pour éviter toute dépendance transitive vers `domain.contracts.canonical`). Duplication volontaire et minimale d'une fonction de transformation (bars→TradingState) documentée en docstring, pour garantir une isolation structurelle réelle plutôt que supposée. Aucun import de `governance.*`, `execution.binder`, `market.adapters.alpaca` — prouvé par tests AST (tests 1-3).

### Architecture Governed — aucune duplication
`apps/naive_vs_governed/comparison.py` réutilise `apps.cockpit.scenarios.run_scenario` et `apps.cockpit.presenter.build_cockpit_view` tels quels (F9). 6 des 7 scénarios (A, B, C, D, F, G) réutilisent directement les `ScenarioSpec` déjà existants (`native_act_paper_success`, `native_hold`, `native_block`, `act_binder_refuses`, `broker_failure`, `external_act`/`external_block`) — aucune nouvelle logique de scénario. Le scénario E (LIVE interdit) ne construit aucun `CycleEngine` : il réutilise `execution.binder.paper_execution.require_paper_mode` tel quel (non modifié) pour prouver le refus structurel avant toute connexion.

### Point découvert et documenté honnêtement — non résolu ici
Le périmètre du seal F10 (`docs/SEAL_SCOPE.md`) inclut `apps/**/*.py`. L'ajout des nouveaux fichiers de démo sous `apps/` fait donc légitimement échouer `tests/unit/test_freeze_manifest.py::test_merkle_seal_exists_and_root_hash_is_recomputable` (83 fichiers attendus au moment du seal vs 87 réellement présents sur cette branche). **Ce n'est pas une régression du code migré** : le seal lui-même (`merkle_seal.json`, `docs/FREEZE_MANIFEST.json`) reste bit-identique au commit F10 (diff vide confirmé) — c'est le test de cohérence qui détecte correctement une dérive de périmètre, exactement son rôle. Aucune tentative n'a été faite pour régénérer le seal ou modifier ce test depuis cette branche de démo — cela reviendrait à masquer le changement, ce qui est explicitement interdit. Décision à prendre séparément par l'utilisateur (scope de seal dédié pour les branches démo, ou régénération explicite lors d'un futur merge).

### Tests
`pytest tests/unit/test_naive_vs_governed.py -q` → **11/11 PASS**.
`pytest tests/ -q` (suite complète, y compris le nouveau fichier) → **183 passed, 1 skipped, 1 failed**. Isolé : sur les 173 tests de la baseline F10, **172 passent, 1 échoue** (le test de cohérence de périmètre du seal, ci-dessus — comportement attendu, pas une régression du code F1-F10). Les 11 nouveaux tests passent tous.

### Statut
DONE, avec le point de seal-scope documenté ci-dessus comme dette explicite de cette branche démo (pas cachée).

## F11 — PROOF_REQUIRED (branche `feature/f11-proof-required`, depuis v0.2.4 / `6864d38`)

### Audit initial (avant tout patch)
`execution/binder/engine.py::_prove()` (avant F11) appelait `self.proof.record(receipt)` dans un `try/except Exception` qui se contentait de logger une note (`echec d'ecriture de la preuve`) sans jamais relever l'exception ni marquer le `CycleOutcome`. Deux consequences non documentees jusqu'ici :
1. Le `CycleOutcome` retourne a l'appelant ne portait **aucune indication** que la persistance avait echoue -- `outcome.error` reste `None`, un cycle apparemment normal.
2. `_last_receipt_hash` avancait quand meme sur le hash du receipt **jamais persiste**, ce qui aurait casse la chaine reellement stockee au prochain cycle reussi (son `previous_receipt_hash` aurait pointe vers un hash absent du store).

`execution/binder/engine.py::_execute()` (F3/F6) avait deja un mecanisme de preuve pre-execution, mais via `order_ledger` (pas `proof`/`CycleReceipt`) : `order_ledger.append(SUBMISSION_INTENT_RECORDED)` avant tout `broker.submit()` -- si cette ecriture echoue, l'execution est refusee avant tout appel broker. Ce mecanisme existant satisfait deja partiellement l'invariant "pas d'action sans preuve pre-execution", mais uniquement cote ledger, pas cote port de preuve (`ProofPort`).

### Risque identifie
`broker side effect succeeds` + `proof persistence fails` : un ordre PAPER peut etre reellement accepte par le broker alors que le `CycleReceipt` final echoue a se persister durablement. Aucune transaction atomique n'existe (ni ne peut exister honnetement) entre le store de preuve local et l'API broker externe.

### Architecture retenue
Changement minimal, pas de reecriture :
- `execution/binder/proof_policy.py` (nouveau) : `ProofPolicy` (`BEST_EFFORT` par defaut, `REQUIRED`) et `ProofOutcome` (`NOT_APPLICABLE`, `PROVEN`, `PRE_EXECUTION_PROOF_FAILURE`, `ABSTENTION_PROOF_INCOMPLETE`, `EXECUTION_SUCCEEDED_PROOF_INCOMPLETE`).
- `CycleEngine.__init__` accepte `proof_policy` (defaut `BEST_EFFORT`, retro-compatible avec tous les appelants existants).
- `_execute()` : sous `ProofPolicy.REQUIRED` uniquement, une lecture legere (`self.proof.last_hash()`, jamais une ecriture) sonde la joignabilite du port de preuve **avant** tout appel broker. Si elle echoue, l'execution est refusee, aucun ordre ne part (`ExecutionResult.not_submitted`). C'est la seule difference comportementale de `REQUIRED` -- le reste (rapport honnete post-execution) est identique dans les deux politiques, car mentir sur l'issue n'est jamais acceptable quelle que soit la politique.
- `_prove()` : `self.proof.record(receipt)` est toujours tente ; en cas d'echec, `_last_receipt_hash` **n'avance plus** (corrige le bug de derive de chaine decrit ci-dessus, independamment de la politique), et `CycleOutcome.proof_outcome` porte `EXECUTION_SUCCEEDED_PROOF_INCOMPLETE` si `execution.touched_the_market` etait vrai, sinon `ABSTENTION_PROOF_INCOMPLETE`. Jamais "rien ne s'est passe", jamais "echec d'execution" quand le broker a pu accepter l'ordre.
- `CycleOutcome` gagne un champ `proof_outcome` (valeur par defaut `NOT_APPLICABLE`, retro-compatible).
- `paper_execution.py::build_paper_cycle_engine` expose `proof_policy` (defaut `BEST_EFFORT`, inchange pour tous les appelants existants -- Cockpit, demo Naive vs Governed, F8.5/F8.6).
- Pourquoi pas un receipt "pre-execution attempt" separe via le `ProofPort` (option evoquee dans la demande) : le mecanisme `order_ledger` remplit deja ce role pour la durabilite de l'intention, et creer un second systeme de preuve pre-execution via `CycleReceipt` aurait duplique une garantie deja tenue ailleurs -- contraire a la consigne "pas de second systeme parallele".

### Fichiers modifies
- `execution/binder/proof_policy.py` (nouveau)
- `execution/binder/engine.py` (constructeur, `_execute`, `_prove`, `CycleOutcome`, docstring)
- `execution/binder/paper_execution.py` (parametre `proof_policy` expose, retro-compatible)
- `tests/integration/test_proof_required.py` (nouveau, 10 tests)

### Nouveaux invariants
1. Un receipt jamais persiste ne fait jamais avancer la chaine en memoire.
2. `EXECUTION_SUCCEEDED_PROOF_INCOMPLETE` != succes, != echec : incertitude reelle preservee, jamais resolue silencieusement.
3. Sous `ProofPolicy.REQUIRED`, un port de preuve injoignable bloque l'execution **avant** tout appel broker.
4. `proof != authority` : aucun de ces changements ne touche `KX108GovernanceBridge`, l'autorite du Binder, ou le contrat canonique.

### Tests ajoutes (10, mapping avec les 13 cas demandes)
1-2 (HOLD/BLOCK, `proof` reel) . 3 (ACT+Binder refuse) . 4 (proof injoignable avant execution, bloque sous REQUIRED, pas sous BEST_EFFORT -- 2 tests) . 5 (succes complet prouve) . 6 (echec broker durablement prouve) . 7 (succes broker + echec preuve finale = `EXECUTION_SUCCEEDED_PROOF_INCOMPLETE`, + variante HOLD = `ABSTENTION_PROOF_INCOMPLETE`) . chaine (receipt fantome n'avance jamais le pointeur, `ReceiptChainVerifier` confirme `VALID`). Cas 8-13 (idempotence, replay, hash-chain/alteration, Native/External, PAPER only) : couverts par les tests F6/F7/F8.5/F8.6 existants, inchanges par F11 (`BEST_EFFORT` par defaut y preserve le comportement exact d'avant F11) -- non dupliques.

### Resultat pytest
`pytest tests/ -q` -> **197 passed, 1 skipped, 1 failed**. Le seul echec est le test de coherence de perimetre du seal (`test_freeze_manifest.py`, attendu et documente : deux nouveaux fichiers de production sous `execution/binder/` font passer le compte scelle de 87 a 88 -- le seal v0.2.4 n'a pas ete touche, conformement a la consigne "ne repare pas le seal au milieu du chantier").

### Regressions
**0 / 188** (baseline exacte preservee). +10 nouveaux tests, le seul delta de comptage est le flip attendu du test de seal.

### Dette restante (volontairement non resolue par F11)
- Pas de vraie transaction distribuee entre le proof store et l'API broker (assume comme limite reelle, pas une dette a combler par un mensonge architectural).
- `ProofPolicy.REQUIRED` n'est pas le defaut de `build_paper_cycle_engine` -- un appelant doit l'activer explicitement pour le chemin gouverne critique.
- Aucun mecanisme de reprise automatique (retry/replay) pour re-tenter la persistance d'un receipt en `EXECUTION_SUCCEEDED_PROOF_INCOMPLETE` -- l'etat est honnetement expose, pas resolu.
- Vrai Kernel X-108 toujours non branche (inchange, hors perimetre F11).

### Verdict
**F11_PROOF_REQUIRED_CLOSED**
