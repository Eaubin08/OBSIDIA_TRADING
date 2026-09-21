"""
TEST-ONLY / NON-PRODUCTION.

Ce module ne doit JAMAIS etre importe depuis governance/, execution/,
market/, native/, simulation/ ou tout autre chemin de configuration
production. Il vit exclusivement sous tests/ precisement pour rendre cet
import impossible par accident (aucun package de production n'a de raison
de dependre de tests/).

`FixtureKX108Client` simule un verdict KX108 fixe pour tester le cablage
Governance Bridge -> Binder -> Alpaca (F6) en l'absence de tout Kernel X-108
reel. Il ne contient AUCUNE logique metier : il retourne exactement ce qu'on
lui demande de retourner, rien de plus.

Regles strictes (verifiees par
tests/integration/test_paper_execution_pipeline.py::
test_fixture_client_not_loadable_from_production_config) :
  - jamais reference dans .env.example, AlpacaConfig, ou governance/bridge/ ;
  - jamais un fallback automatique de UnavailableKX108Client ;
  - leve un RuntimeWarning a l'instanciation, visible mais non bloquant.
"""
from __future__ import annotations

import warnings
from typing import Any, Dict


class FixtureKX108Client:
    """TEST-ONLY / NON-PRODUCTION — verdict KX108 fixe, aucune logique metier."""

    def __init__(self, verdict: str = "HOLD") -> None:
        warnings.warn(
            "FixtureKX108Client instancie : TEST-ONLY, ne doit jamais tourner "
            "en production. Si vous voyez cet avertissement en dehors de "
            "tests/, c'est un bug de cablage.",
            RuntimeWarning,
            stacklevel=2,
        )
        self._verdict = verdict

    def set_next_verdict(self, verdict: str) -> None:
        self._verdict = verdict

    def evaluate_trading(self, ir_payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"verdict": self._verdict, "source": "FixtureKX108Client (TEST-ONLY)"}
