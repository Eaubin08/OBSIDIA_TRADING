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
