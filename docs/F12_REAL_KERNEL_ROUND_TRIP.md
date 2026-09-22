# F12 — Real KX108 Kernel Round-Trip Evidence

## Kernel identifié

- Source : `C:\Users\User\Desktop\obsidia-engine-proof-core\obsidia-x108-proofs_REMOTE_A5F21C6B\server.kernel.sealed.cjs` (fichier scellé, LU mais JAMAIS modifié)
- Commit core au moment du test : `c306fa33` (`docs(udip): freeze universal domain integration protocol v0`)
- Transport : HTTP, Express.js, port `3001`, route `POST /kernel/ragnarok` — exactement l'URL par défaut de `domains/trading/trading_x108_gate.py::KERNEL_URL`
- Interface interne : le serveur spawn `python -u sigma/run_pipeline.py <domain> <data_json>` et relaie le JSON stdout comme réponse HTTP

## Démarrage (lecture seule, aucune modification)

```
node server.kernel.sealed.cjs
```
Sortie observée : `TRINITY KERNEL : CONNECTÉ & OPÉRATIONNEL — Listening on port 3001...`

## Requête réelle envoyée (payload IR exact du gate)

```json
{"domain":"trading","data":{"T_mean":0.9,"H_score":0.9,"A_score":0.1,"S":0.6},"meta":{"flow_type":"BUY","ir_intent":"CREATE_PATCH","risk_class":"","gate_version":"v1"}}
```

- request_digest (SHA-256) : `a79eec77fe79d8aa4d4e7cb9eba3e20ab75fdbc624d29fa3fa96e973f38b9b63`
- response_digest (SHA-256) : `d921572c3b01aa1bacbdd45add9e154e9df6ea40318fcaf9f29a0f3a3812d552`
- HTTP status : `200`, ~0.22s
- Timestamp : 2026-09-22 (session courante)

## Contrat réel constaté (PAS supposé)

Réponse réelle : objet JSON à 40+ clés, notamment `x108_gate`, `market_verdict`, `business_semantic_verdict`, `reason_code`, `unknowns`, `contradictions`, `risk_flags`, `decision_id`, `severity`.

**Découverte critique** : la clé attendue par le code du gate actuel (`kernel_decision.get("verdict", "HOLD")`) est **absente** de la réponse réelle. Le Kernel réel expose `x108_gate`, pas `verdict`. Ceci est un fait constaté par ce round-trip, pas une supposition — c'est un écart de contrat préexistant côté core (gate actuel), pas une régression introduite ici. Aucune modification n'a été apportée au core pour cette raison — la correction (normalisation `x108_gate`→`verdict`) est faite côté Trading uniquement, dans `RealKX108Client`.

Pour ce payload précis :
```
x108_gate = HOLD
reason_code = P3T9B_TRUSTED_METADATA_REQUIRED
severity = S2
unknowns = []
contradictions = []
risk_flags = []
decision_id = trading-9450afd4c149
```

Interprétation stricte, sans causalité inventée : **input contained flow_type=BUY avec métadonnées d'action non fournies (irreversible/action_type/intent absents du payload IR standard du gate) → Kernel returned x108_gate=HOLD, reason_code=P3T9B_TRUSTED_METADATA_REQUIRED.** Rien de plus n'est affirmé — notamment pas de lien causal entre `unknowns`/`contradictions` (vides ici) et le HOLD.

## Frontière — confirmé après le test

```
KERNEL FILES MODIFIED = 0   (git status --short sur le core : seul le diff merkle_seal.json préexistant, non lié à ce test)
KERNEL COMMITS CREATED = 0  (git log -1 inchangé : c306fa33)
KERNEL TAGS MOVED = 0
```

Le serveur a écrit un fichier de preuve (`MonProjet/allData/decision_trading_*.json`) — comportement normal et voulu du serveur lui-même (persistance de preuve scellée), pas une modification de code Kernel ; ce fichier n'apparaît pas dans `git status --short` (hors suivi git).

## Conclusion

`REAL_KERNEL_ROUND_TRIP = PASS`. Le Kernel réel a été joint, a répondu, et la réponse a été observée et documentée fidèlement. Le contrat de sortie réel diffère du contrat supposé par le gate actuel (`x108_gate` vs `verdict`) — `RealKX108Client` (côté Trading) normalise cet écart sans jamais inventer de valeur en cas d'absence/ambiguïté.
