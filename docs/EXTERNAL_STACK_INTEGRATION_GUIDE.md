# Guide d'intégration d'une stack Trading externe

> Pour toute personne (ex: mon frère) ou entreprise qui possède déjà ses propres agents,
> règles, stratégies ou modèles de trading et veut les brancher sur la gouvernance Obsidia
> **sans les réécrire et sans les recréer**.
>
> **Statut au moment de ce document** : aucune vraie stack externe n'est encore branchée.
> Ce guide décrit le contrat à respecter et l'exemple pédagogique (`ExampleBrotherStackAdapter`)
> qui sert uniquement à démontrer la forme attendue — ce n'est pas une intégration réelle.

## Ce que vous pouvez construire librement

Tout ce qui produit un signal de trading : vos agents, vos indicateurs, vos règles de
décision, vos modèles statistiques ou de machine learning, vos données de marché, votre
propre calibration. **Obsidia ne connaît rien de tout ça et n'a pas besoin de le connaître.**

## Ce qu'Obsidia attend de votre stack

Un objet `ExternalSignal` (`external/contracts/external_signal.py`) par proposition de
trading. Les champs obligatoires :

| Champ | Type | Exemple |
|---|---|---|
| `source_id` | str | `"ma_strategie_momentum_v3"` |
| `organization_id` | str | `"ma_societe"` |
| `symbol` | str | `"AAPL"` |
| `signal` | str | `"BUY"` / `"SELL"` / `"HOLD"` |
| `confidence` | float | `0.7` |
| `rationale` | str | `"prix au-dessus de la moyenne 50j, volume en hausse"` |

Champs optionnels, à fournir si votre stack les produit — **jamais inventés s'ils sont absents** :

| Champ | Rôle |
|---|---|
| `strategy_id` | distingue plusieurs stratégies d'une même source |
| `unknowns` | ce que votre stack ne sait pas évaluer pour ce cas |
| `contradictions` | signaux internes contradictoires que vous avez détectés |
| `risk_flags` | risques identifiés (liquidité faible, données incomplètes...) |
| `evidence_refs` | références vers vos propres preuves/logs |
| `observed_at` | timestamp Unix de votre observation (permet de détecter un signal périmé) |
| `calibration` | métadonnées de VOTRE calibration (voir plus bas) |

## Ce que vous n'avez PAS à recréer

- **KX108** : l'autorité de décision. Vous ne décidez jamais ACT/HOLD/BLOCK — vous proposez,
  Obsidia décide.
- **Le Binder** : la barrière d'exécution. Même si KX108 dit ACT, le Binder peut encore refuser.
- **Le Receipt/Proof** : la preuve chaînée est produite automatiquement pour vous.
- **Le Replay** : la capacité de rejouer un cycle sans effet de bord existe déjà.

Vous n'avez besoin d'aucun de ces éléments dans votre code. Ils vivent dans le repo principal,
vous n'y touchez jamais.

## Comment votre signal entre dans Obsidia

```
Votre stack (agents/modèle/règles)
        ↓
ExternalSignal.from_raw_payload(votre_payload)   ← validation stricte, rejette si champ manquant
        ↓
normalize_external_signal(signal, adapter_id=...)  ← traduit vers le contrat canonique
        ↓
même Governance Bridge que le chemin natif Obsidia
        ↓
KX108 (vraie autorité ou fixture de test selon l'environnement)
        ↓
Binder → exécution PAPER uniquement → Receipt
```

Après l'étape de normalisation, votre signal est **structurellement indistinguable** d'un
signal produit par les agents natifs d'Obsidia pour toute la suite du pipeline — seule sa
provenance (`source_system=external`) le distingue, à titre informatif uniquement (elle ne
change jamais le comportement de la gouvernance).

## Unknowns, risques, evidence : comment les fournir

Ne remplissez **jamais** ces champs pour "faire bien" ou "avoir l'air complet". Un tuple vide
signifie "non rapporté par votre source", pas "vérifié comme absent". Si votre stack sait
détecter une incertitude réelle, mettez-la dans `unknowns`. Si votre stack sait qu'un risque
existe (données incomplètes, marché fermé, latence élevée...), mettez-le dans `risk_flags`.
Rien de tout ça n'est jamais inventé à votre place.

## Calibration externe (optionnelle)

Si votre stack a sa propre calibration (paramètres estimés sur vos propres données), vous
pouvez la déclarer :

```python
"calibration": {
    "external_calibration_id": "ma_calib_2026_q3",
    "dataset_reference": "mon_dataset_interne_v2",
    "calibration_version": "v2",
    "created_at": 1735000000.0,
    "valid_until": 1737000000.0,
    "evidence_refs": ["mon:evidence:ref"],
}
```

**Le `CalibrationPack` natif d'Obsidia (basé sur des données Alpaca AAPL) ne vous est jamais
imposé.** Si vous ne fournissez rien, votre signal porte l'indicateur explicite
`NO_EXTERNAL_CALIBRATION_INFORMATION` — jamais une calibration fabriquée à votre place.

## Comment tester votre connecteur

Implémentez le Protocol `ExternalTradingStackPort` (alias de `ExternalStackAdapter`,
`external/adapters/base_adapter.py`) :

```python
class MonAdapter:
    adapter_id = "ma_stack_v1"
    organization_id = "ma_societe"

    def fetch_signals(self, symbol: str) -> Sequence[ExternalSignal]:
        # interrogez votre stack ici, retournez des ExternalSignal validés
        ...
```

Regardez `external/examples/brother_stack/example_adapter.py` — **c'est une fixture
pédagogique, pas une vraie stack** — pour voir la forme exacte attendue. Les tests
`tests/unit/test_external_adapter.py` et `tests/unit/test_external_stack_readiness_f15.py`
montrent tous les cas limites (champ manquant, symbole incohérent, signal périmé,
calibration absente/présente) que votre propre connecteur devrait aussi couvrir.

## Exemple minimal de payload

```json
{
  "source_id": "ma_strategie_momentum_v3",
  "organization_id": "ma_societe",
  "symbol": "AAPL",
  "signal": "BUY",
  "confidence": 0.65,
  "rationale": "momentum positif sur 20 jours, volume confirmant",
  "observed_at": 1735000000.0,
  "unknowns": ["pas_de_donnee_options"],
  "risk_flags": ["volatilite_recente_elevee"]
}
```

## Ce qui reste hors de portée de ce guide

Ce document ne couvre que le **contrat d'entrée**. Il ne dit rien sur :
- comment structurer vos propres agents en interne (c'est votre choix) ;
- comment calibrer vos propres modèles (c'est votre méthode) ;
- quand KX108 décidera ACT/HOLD/BLOCK pour votre signal (c'est l'autorité de gouvernance,
  indépendante de la provenance native ou externe du signal).
