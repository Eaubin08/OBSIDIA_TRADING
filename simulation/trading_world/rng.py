"""
PRNG seede pour replay deterministe.

Port fidele de l'algorithme mulberry32 de la source TypeScript
(Obsidia-lab-trad: os4-platform/server/engines/tradingEngine.ts, L8-17).

Choix documente : plutot que d'utiliser `random.Random(seed)` ou
`numpy.random.default_rng(seed)` (dont l'algorithme interne est different
de mulberry32 et ne produirait donc pas la meme sequence que la source
historique meme pour un seed identique), ce module reimplemente
l'algorithme exact en arithmetique 32 bits non signee. La consigne de
fusion n'exigeait pas une reproduction bit-a-bit de la source TS, mais
l'obtenir ici est peu couteux (8 lignes) et evite d'introduire une
troisieme famille de PRNG dans l'ecosysteme Obsidia. La garantie exigee
— meme seed -> meme sequence exacte a chaque execution Python, seed
different -> sequence differente — est de toute facon assuree par
construction (etat interne pur, aucune source d'entropie externe).
"""
from __future__ import annotations

import math

_MASK32 = 0xFFFFFFFF


def _u32(x: int) -> int:
    return x & _MASK32


def _imul32(a: int, b: int) -> int:
    """Equivalent de Math.imul: produit tronque aux 32 bits de poids faible."""
    return _u32(a * b)


class Mulberry32:
    """PRNG seede deterministe. `random()` retourne un flottant dans [0, 1)."""

    __slots__ = ("state",)

    def __init__(self, seed: int) -> None:
        self.state = _u32(seed)

    def random(self) -> float:
        self.state = _u32(self.state + 0x6D2B79F5)
        s = self.state
        t = _imul32(s ^ (s >> 15), s | 1)
        t2 = _u32(t + _imul32(t ^ (t >> 7), t | 61))
        t2 = _u32(t2 ^ t)
        result = _u32(t2 ^ (t2 >> 14))
        return result / 4294967296.0


def box_muller(rand) -> float:
    """
    Tire une variable normale standard N(0,1) via la methode Box-Muller,
    en consommant deux appels a `rand()` (fonction sans argument -> float
    dans [0,1), typiquement `Mulberry32.random`).
    """
    u = rand()
    v = rand()
    return math.sqrt(-2.0 * math.log(u + 1e-15)) * math.cos(2.0 * math.pi * v)
