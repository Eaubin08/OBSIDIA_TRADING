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

<!-- Les entrées suivantes seront ajoutées phase par phase (F2, F3, F4...). Ne pas pré-remplir avant migration réelle. -->
