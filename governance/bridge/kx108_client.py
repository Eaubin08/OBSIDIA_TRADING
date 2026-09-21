"""
Governance Bridge — interface vers KX108 (chantier F5).

AUCUN vrai Kernel X-108 n'est accessible depuis ce repo (voir
docs/B15_STRUCTURAL_SCORE_BOUNDARY.md). Ce module ne recree donc PAS de
Kernel local : il definit le contrat d'appel (`KX108Client`) et fournit
des implementations honnetes pour ce qui est reellement disponible :

  - `UnavailableKX108Client` : le cas reel par defaut tant qu'aucun vrai
    Kernel n'est branche. Toute tentative d'appel echoue explicitement.
  - `StaticKX108Client` : double de test, retourne un verdict fixe fourni
    par l'appelant — utilise uniquement dans tests/.

Un futur client HTTP reel (ex: vers OBSIDIA_KERNEL_URL, meme forme d'appel
que domains/trading/trading_x108_gate.py::TradingX108Gate.evaluate dans le
core actuel) devra implementer ce meme Protocol, sans changer
governance_bridge.py.
"""
from __future__ import annotations

from typing import Any, Dict, Protocol, runtime_checkable


class KX108Unavailable(RuntimeError):
    """Le Kernel X-108 n'a pas pu etre joint (reseau, timeout, non configure)."""


@runtime_checkable
class KX108Client(Protocol):
    """
    Contrat d'appel au Kernel X-108.

    `evaluate_trading` recoit l'IR payload (meme forme que
    TradingX108Gate.translate_to_ir du core actuel : domain/data/meta) et
    doit retourner un dict portant au moins la cle "verdict"
    (ACT/ALLOW/HOLD/BLOCK). Toute autre garantie de format appartient au
    Kernel reel, pas a ce contrat.
    """

    def evaluate_trading(self, ir_payload: Dict[str, Any]) -> Dict[str, Any]:
        ...


class UnavailableKX108Client:
    """
    Implementation honnete par defaut : aucun Kernel reel n'est branche.

    Toute evaluation leve `KX108Unavailable` — c'est au Governance Bridge
    de traduire cela en fail-closed (Authority.HOLD), jamais a ce client de
    deviner un verdict.
    """

    def evaluate_trading(self, ir_payload: Dict[str, Any]) -> Dict[str, Any]:
        raise KX108Unavailable(
            "aucun Kernel X-108 reel n'est accessible depuis ce repo "
            "(voir docs/B15_STRUCTURAL_SCORE_BOUNDARY.md)"
        )


class StaticKX108Client:
    """
    Double de test : retourne un verdict fixe. RESERVE aux tests — ne doit
    jamais etre utilise comme configuration par defaut en dehors de
    tests/, car il simulerait une reponse KX108 qui n'existe pas.
    """

    def __init__(self, response: Dict[str, Any]) -> None:
        self._response = dict(response)

    def evaluate_trading(self, ir_payload: Dict[str, Any]) -> Dict[str, Any]:
        return dict(self._response)


class RaisingKX108Client:
    """Double de test : leve une exception arbitraire (timeout simule, etc.)."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def evaluate_trading(self, ir_payload: Dict[str, Any]) -> Dict[str, Any]:
        raise self._exc
