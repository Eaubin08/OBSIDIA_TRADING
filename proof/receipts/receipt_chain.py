"""
Obsidia Trading — objet de preuve chaine (chantier F7).

Choix de conception documente : ce module NE DUPLIQUE PAS `CycleReceipt`.
`domain/receipt.py` porte deja, depuis F3, exactement ce qui est demande par
la consigne F7 : chainage par `previous_receipt_hash`, hash sur contenu
horodatage exclu (`decision_hash`), convention de genese explicite
(`GENESIS_HASH = "0"*64`), et un `receipt_schema_version`. Reecrire un
deuxieme objet de preuve aurait cree deux sources de verite pour la meme
notion — exactement le risque que F3.5 a deja corrige une fois pour les
champs semantiques des agents.

Ce module se contente de re-exporter le vocabulaire canonique pour que
`proof/receipts/` soit l'entree documentaire attendue, et ajoute UNE
extension utile a F7 : le format d'attache d'un resultat de simulation
deterministe (seed/params/digest) dans `CycleReceipt.extensions`, necessaire
au replay deterministe (voir replay.py).
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Tuple

from domain.receipt import (
    GENESIS_HASH,
    RECEIPT_SCHEMA_VERSION,
    CycleReceipt,
    Decision,
    canonical_json,
    verify_chain,
)

SIMULATION_EXTENSION_KEY = "f7_simulation"
SIMULATION_KIND_TRADING_WORLD = "trading_world"

__all__ = [
    "GENESIS_HASH",
    "RECEIPT_SCHEMA_VERSION",
    "CycleReceipt",
    "Decision",
    "canonical_json",
    "verify_chain",
    "SIMULATION_EXTENSION_KEY",
    "SIMULATION_KIND_TRADING_WORLD",
    "build_simulation_extension",
]


def _digest(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def build_simulation_extension(
    *,
    kind: str,
    seed: int,
    params: Dict[str, Any],
    engine_version: str,
    steps: List[Any],
    returns: List[float],
) -> Dict[str, Any]:
    """
    Construit le bloc a placer sous `CycleReceipt.extensions["f7_simulation"]`.

    Ne stocke PAS la trajectoire complete si elle est volumineuse : un digest
    suffit a verifier un rejeu (chantier F7 §1 : "digest + reference si un
    objet est gros, ne pas dupliquer inutilement"). Les parametres complets
    (seed inclus) sont conserves integralement : c'est ce qui rend le rejeu
    possible, pas seulement verifiable.
    """
    output_digest = _digest({"steps": steps, "returns": returns})
    return {
        "kind": kind,
        "seed": seed,
        "params": params,
        "engine_version": engine_version,
        "output_digest": output_digest,
        "n_steps": len(steps),
    }
