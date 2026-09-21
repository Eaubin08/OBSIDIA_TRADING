# OBSIDIA_TRADING

Implémentation de référence du domaine Trading gouverné par Obsidia.

## Le flux, en une image

```
Market
  ↓
Trading cognition (agents natifs OU stack externe via adapter)
  ↓
TradeIntent
  ↓
Obsidia Governance (Sigma / Guard)
  ↓
KX108 (seule autorité de décision)
  ↓
Binder (vérifie le verdict, ne le fabrique jamais)
  ↓
Broker adapter (paper d'abord)
  ↓
Receipt (preuve chaînée, ne décide jamais)
```

## Deux chemins, une seule gouvernance

### Native Reference Implementation (`native/`)
Obsidia fournit le domaine Trading complet : agents, stratégies, indicateurs, portfolio, risk, calibration. C'est le laboratoire métier et la vitrine montrable à une entreprise.

### External Stack Adapter (`external/`)
Une entreprise (ou mon frère) garde sa propre stack — ses agents, ses règles, ses données — et la branche à la même gouvernance via un adapter de normalisation. Rien n'est dupliqué côté gouvernance.

**Les deux chemins convergent avant l'autorité**, au niveau du `domain/contracts/` (Canonical Domain Contract). Après ce point, la provenance Native/External ne doit plus jamais changer le comportement de la gouvernance. Il n'y a jamais deux kernels.

## Frontière avec le Core Obsidia

Ce repo ne contient PAS :
- KX108 (le Kernel réel, scellé, externe)
- le Runtime Binder central d'Obsidia
- les invariants du Core

Il contient :
- le contrat nécessaire pour parler à KX108
- des bridges/adapters
- un Binder **local de développement** (mock, pour tester sans dépendre du Core) — voir `execution/binder/`

Objectif : quelqu'un doit pouvoir travailler ici sans jamais avoir besoin d'ouvrir le repo principal Obsidia.

## Règle absolue

Aucun agent, stratégie, adapter, simulation, stack externe, broker ou receipt ne possède l'autorité de décision. Seul KX108 décide (ACT / HOLD / BLOCK). Le Binder vérifie ce verdict, il ne le fabrique jamais.

## État actuel

Voir `docs/MIGRATION_PROVENANCE.md` pour la provenance de chaque composant migré, et `docs/B15_STRUCTURAL_SCORE_BOUNDARY.md` pour la limite connue sur la formule de score structurel (non vérifiable contre le Kernel réel depuis ce repo).

Sources d'audit : `C:\Users\User\Desktop\OBSIDIA_TRADING_AUDIT_2026\` (généalogie, inventaire, gap analysis, matrice de migration — non dupliqués ici, consultés en lecture seule).

## Paper trading uniquement

Cible V1 : données de marché réelles + cognition Trading réelle + gouvernance Obsidia réelle + **ordres paper Alpaca uniquement** + receipts réels. Aucun ordre live, aucune clé secrète dans ce repo (variables d'environnement uniquement, voir `.env.example`).
