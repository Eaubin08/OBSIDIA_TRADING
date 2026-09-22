"""
Governance Bridge — interface vers KX108 (chantier F5, etendu F12).

Ce module ne recree JAMAIS de Kernel local : il definit le contrat d'appel
(`KX108Client`) et fournit des implementations honnetes :

  - `UnavailableKX108Client` : fail-closed par defaut tant qu'aucun Kernel
    n'est explicitement configure. Toute tentative d'appel echoue.
  - `RealKX108Client` (F12) : transport HTTP reel vers un Kernel X-108
    reellement accessible (meme route que
    domains/trading/trading_x108_gate.py::TradingX108Gate.evaluate dans le
    core Obsidia — POST {domain,data,meta} -> JSON). AUCUNE intelligence
    decisionnelle : transporte, valide, normalise, ne decide jamais.
  - `StaticKX108Client` / `RaisingKX108Client` : doubles de test — utilises
    uniquement dans tests/.

F12 a confirme par un round-trip reel (voir
docs/F12_REAL_KERNEL_ROUND_TRIP.md) que le Kernel reel repond avec la cle
`x108_gate` (ACT/ALLOW/HOLD/BLOCK), PAS `verdict` — `RealKX108Client`
normalise ce champ vers "verdict" sans jamais inventer une valeur : si le
champ est absent/invalide, il ne le fabrique pas, et le Governance Bridge
fail-close (Authority.HOLD) exactement comme prevu par _parse_authority.
"""
from __future__ import annotations

import os

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


_VALID_KERNEL_AUTHORITIES = {"ACT", "ALLOW", "HOLD", "BLOCK"}


class RealKX108Client:
    """
    Client HTTP reel vers un Kernel X-108 reellement accessible (F12).

    Reprend exactement la route/forme d'appel de
    domains/trading/trading_x108_gate.py::TradingX108Gate.evaluate dans le
    core Obsidia (POST {domain,data,meta} -> JSON). Ne contient AUCUNE
    logique de decision : transport + validation + normalisation
    uniquement. Toute anomalie (indisponible, timeout, JSON invalide,
    schema inconnu, verdict absent/inconnu) est fail-closed :
    `KX108Unavailable` est levee, jamais une valeur devinee.

    Le Kernel reel observe en F12 retourne la cle `x108_gate`
    (ACT/ALLOW/HOLD/BLOCK), pas `verdict` — ce client normalise ce champ
    UNIQUEMENT s'il est present et dans l'ensemble de valeurs attendu ;
    sinon le dict retourne ne porte pas de "verdict" exploitable et le
    Governance Bridge fail-close lui-meme (_parse_authority), sans que ce
    client n'ait besoin de deviner quoi que ce soit.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url or os.environ.get(
            "OBSIDIA_KERNEL_URL", "http://127.0.0.1:3001/kernel/ragnarok"
        )
        self._timeout = timeout

    def evaluate_trading(self, ir_payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            import requests  # import local : evite une dependance dure si non utilise
        except ImportError as exc:  # pragma: no cover - requests est dans requirements.txt
            raise KX108Unavailable(f"module requests indisponible: {exc}") from exc

        try:
            response = requests.post(
                self._base_url, json=ir_payload, timeout=self._timeout
            )
            response.raise_for_status()
        except Exception as exc:
            raise KX108Unavailable(
                f"Kernel X-108 injoignable ou erreur transport: {exc}"
            ) from exc

        try:
            kernel_response = response.json()
        except Exception as exc:
            raise KX108Unavailable(
                f"reponse Kernel X-108 non-JSON (contrat invalide): {exc}"
            ) from exc

        if not isinstance(kernel_response, dict):
            raise KX108Unavailable(
                f"reponse Kernel X-108 malformee (attendu un objet JSON, recu {type(kernel_response).__name__})"
            )

        normalized = dict(kernel_response)
        if "verdict" not in normalized:
            raw_authority = normalized.get("x108_gate")
            if (
                isinstance(raw_authority, str)
                and raw_authority.strip().upper() in _VALID_KERNEL_AUTHORITIES
            ):
                normalized["verdict"] = raw_authority.strip().upper()
            # Sinon : ne rien inventer. Le Governance Bridge fail-close
            # lui-meme sur l'absence de "verdict" exploitable.
        normalized.setdefault("source", "KX108_REAL")
        return normalized
