# B15 Structural Score — Boundary Note

## Ce que B15 était
Dans `agent-trad-main` (sept. 2026), le score structurel `S = alpha*T + beta*H - gamma*A` mélangeait des unités incompatibles : `T` et `H` sont des cohérences bornées [0,1], mais `A` (dispersion) avait une échelle non normalisée. Résultat : `S` ne pouvait jamais dépasser 0.167 alors que le seuil `theta_S` était fixé à 0.25 — **aucune action ACT n'était structurellement atteignable**.

## Correction appliquée dans agent-trad-main
Commit `a6b271a` (Option C) : `A_norm = A/(n-1)`, `S = clamp(((alpha*T+beta*H)/(alpha+beta)) * (1-gamma*A_norm), 0, 1)`, seuil recalibré à 0.20. Validée par 90→214 tests, tenue jusqu'au freeze final.

## Ce qui a été vérifié dans le core Obsidia actuel (`obsidia-x108-proofs`)
Le fichier `domains/trading/trading_x108_gate.py` (et ses jumeaux `bank_x108_gate.py`, `gps_x108_gate.py`) **ne calcule pas S localement**. Les champs `T_mean`, `H_score`, `A_score`, `S` sont un pur pass-through du payload entrant, transmis tel quel à un **Kernel X-108 externe, scellé, hors périmètre inspectable**. Le calcul réel (formule alpha/beta/gamma, normalisation de A, comparaison au seuil) a lieu exclusivement côté Kernel.

## Conséquence pour ce repo

**Il est impossible, depuis `OBSIDIA_TRADING`, de vérifier si le Kernel X-108 réel reproduit le bug B15 ou une correction équivalente.**

Décision appliquée dans ce repo :
1. La formule corrigée d'agent-trad-main (Option C) est conservée comme **`domain signal` / reference implementation** — utile pour développer, tester et démontrer le domaine en mode SIM/PAPER local, sans dépendance au Kernel réel.
2. Elle **n'a jamais l'autorité finale**. Elle ne fait que produire un signal d'entrée soumis à la gouvernance.
3. Quand la phase Governance (F5) sera activée en intégration réelle, le score doit être recalculé — ou validé — par le vrai KX108 via son contrat existant (`governance/bridge/`). La version locale ne doit jamais se substituer à lui.
4. Toute divergence entre le signal local et le verdict du Kernel réel doit être journalisée (pattern `gap_status`, voir `apps/naive_vs_governed/`), jamais résolue silencieusement en faveur de l'un ou l'autre.

## Provenance
- Formule : `native/indicators/structural_score.py` (portée depuis `agent-trad-main: agents/indicators.py`, post-B15)
- Analyse originale : voir `AGENT_TRAD_MAIN_BACKUP_20260921/11_B7_B8_B15_ANALYSIS.md` et `13_POST_B15_FREEZE.md` (source read-only, non dupliquée ici)
