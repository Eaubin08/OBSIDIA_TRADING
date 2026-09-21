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

<!-- F3 ci-dessous -->
