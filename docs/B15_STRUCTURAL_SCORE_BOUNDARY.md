# B15 Structural Score — Boundary Note

## Ce que B15 était
Dans `agent-trad-main` (sept. 2026), le score structurel `S = alpha*T + beta*H - gamma*A` mélangeait des unités incompatibles : `T` et `H` sont des cohérences bornées [0,1], mais `A` (dispersion) avait une échelle non normalisée. Résultat : `S` ne pouvait jamais dépasser 0.167 alors que le seuil `theta_S` était fixé à 0.25 — **aucune action ACT n'était structurellement atteignable**.

## Correction appliquée dans agent-trad-main
Commit `a6b271a` (Option C) : `A_norm = A/(n-1)`, `S = clamp(((alpha*T+beta*H)/(alpha+beta)) * (1-gamma*A_norm), 0, 1)`, seuil recalibré à 0.20. Validée par 90→214 tests, tenue jusqu'au freeze final.

## Ce qui a été vérifié dans le core Obsidia actuel (`obsidia-x108-proofs`)
Le fichier `domains/trading/trading_x108_gate.py` (et ses jumeaux `bank_x108_gate.py`, `gps_x108_gate.py`) **ne calcule pas S localement**. Les champs `T_mean`, `H_score`, `A_score`, `S` sont un pur pass-through du payload entrant, transmis tel quel à un **Kernel X-108 externe, scellé, hors périmètre inspectable**. Le calcul réel (formule alpha/beta/gamma, normalisation de A, comparaison au seuil) a lieu exclusivement côté Kernel.

## Conséquence pour ce repo

**KNOWN BOUNDARY — LOCAL SIGNAL VERIFIED / REAL KX108 FORMULA NOT VERIFIED FROM THIS REPO.**

Il est impossible, depuis `OBSIDIA_TRADING`, de vérifier si le Kernel X-108 réel reproduit le bug B15 ou une correction équivalente. Cette limite est structurelle (le Kernel est scellé, hors périmètre), pas un oubli d'audit.

Décision appliquée dans ce repo (mise en œuvre concrète en F5 — Governance Bridge) :
1. La formule corrigée d'agent-trad-main (Option C) est portée dans `governance/bridge/local_signal.py::compute_local_structural_signal` et utilisée comme **evidence/signal local** — utile pour développer, tester et démontrer le domaine en mode SIM/PAPER local, sans dépendance au Kernel réel.
2. Elle **n'a jamais l'autorité finale**. `KX108GovernanceBridge` (`governance/bridge/governance_bridge.py`) l'attache uniquement au champ `Decision.structural_score` — jamais à `Decision.authority`. Le score local ne peut ni produire `ACT` lui-même, ni transformer un `HOLD`/`BLOCK` renvoyé par KX108 en `ACT` (vérifié par `tests/unit/test_governance_bridge.py`, tests 1-3).
3. Le verdict d'autorité (`ACT`/`HOLD`/`BLOCK`) provient EXCLUSIVEMENT du champ `"verdict"` de la réponse du `KX108Client` injecté. Tant qu'aucun vrai Kernel n'est branché (`UnavailableKX108Client`), le système est **fail-closed** : indisponibilité ou réponse invalide → `Authority.HOLD` systématique, jamais `ACT` par défaut (tests 4-5).
4. Toute divergence entre le signal local et le verdict du Kernel réel voyage dans `Decision.metrics["local_signal"]` et `Decision.metrics["kx108_response"]` — journalisée dans le receipt, jamais résolue silencieusement en faveur de l'un ou l'autre.

## Provenance
- Formule locale : `governance/bridge/local_signal.py` (portée depuis `agent-trad-main: agents/indicators.py::structural_score`, post-B15 — `triangle_mean`/`asymmetry_penalty` COPY_AS_IS ; `build_coherence_matrix` ADAPT depuis `core/guard_x108.py::_build_coherence_matrix`, entrée changée de l'ancien `AgentVote.signal` vers `domain.proposal.AgentOutput.signal` du roster natif à 17 agents)
- Pont vers KX108 : `governance/bridge/{governance_bridge,ir_payload,kx108_client}.py` (F5, nouveau code — voir `docs/MIGRATION_PROVENANCE.md`)
- Analyse originale : voir `AGENT_TRAD_MAIN_BACKUP_20260921/11_B7_B8_B15_ANALYSIS.md` et `13_POST_B15_FREEZE.md` (source read-only, non dupliquée ici)
