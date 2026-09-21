"""
Obsidia Trading — port horloge.

Piece la plus discrete du socle, et pourtant celle qui rend le chantier §25
possible. Le prototype appelle `time.time()` directement a trois endroits
(GuardX108 pour le verrou et l'horodatage de l'artifact, MockMarketFeed pour
son terme cyclique). Consequence mesuree : deux rejeux du meme etat ne
produisent ni la meme trajectoire, ni le meme hash (bugs B6 et B16).

En passant par un port, le temps devient une entree du systeme comme une
autre — donc reproductible.
"""
from __future__ import annotations

import time
from typing import Protocol, runtime_checkable


@runtime_checkable
class ClockPort(Protocol):
    """Source de temps du systeme."""

    def now(self) -> float:
        """Instant courant, en secondes depuis l'epoch."""
        ...


class SystemClock:
    """Horloge reelle. Utilisee en PAPER et en LIVE."""

    def now(self) -> float:
        return time.time()


class FrozenClock:
    """
    Horloge deterministe, avancant d'un pas fixe a chaque lecture.

    Destinee aux tests, au rejeu et aux scenarios reproductibles. Le pas par
    defaut d'une seconde suffit a departager deux evenements successifs tout
    en restant previsible.
    """

    def __init__(self, start: float = 1_704_067_200.0, step: float = 1.0) -> None:
        self._current = start
        self._step = step

    def now(self) -> float:
        value = self._current
        self._current += self._step
        return value

    def peek(self) -> float:
        """Prochaine valeur qui sera retournee, sans faire avancer l'horloge."""
        return self._current

    def reset(self, start: float = 1_704_067_200.0) -> None:
        self._current = start


class FixedClock:
    """Horloge immobile : renvoie toujours le meme instant."""

    def __init__(self, instant: float = 1_704_067_200.0) -> None:
        self._instant = instant

    def now(self) -> float:
        return self._instant
