"""
SizingPolicy — configuration explicite de dimensionnement (P1-C, chantier §11).

Aucune valeur financiere/risque n'a de defaut implicite. Tout champ absent
(None) signifie "aucune contrainte configuree sur cet axe", jamais "0" ou
"illimite par defaut" au sens favorable. L'engine (native_reference_sizing.py)
est responsable de refuser explicitement quand la configuration minimale
necessaire (une base de sizing + un quantity_increment) est absente.

Exactement UNE base de sizing peut etre configuree : target_notional OU
target_fraction_of_equity. Les deux ensemble, ou aucune des deux, sont des
configurations invalides (detectees ici pour les deux-a-la-fois, et par
l'engine pour aucune-des-deux, puisque "aucune base" est un etat valide de
policy qui doit produire un SizingDecision REJECTED plutot qu'une exception
a la construction).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SizingPolicy:
    """
    Politique de dimensionnement fournie par le produit, jamais devinee par
    le code. Chaque champ est un plafond ou une base explicitement choisie ;
    aucun pourcentage par defaut, aucun levier par defaut.
    """

    # Base de sizing — exactement une des deux doit etre configuree.
    target_notional: Optional[float] = None
    target_fraction_of_equity: Optional[float] = None

    # Plafonds — chacun optionnel, chacun applique seulement si configure.
    max_notional: Optional[float] = None
    max_fraction_of_equity: Optional[float] = None
    max_fraction_of_buying_power: Optional[float] = None
    max_symbol_exposure: Optional[float] = None
    max_portfolio_gross_exposure: Optional[float] = None
    max_concentration: Optional[float] = None
    max_drawdown_for_new_risk: Optional[float] = None

    # Normalisation — obligatoire pour toute quantite positive.
    quantity_increment: Optional[float] = None

    def __post_init__(self) -> None:
        if self.target_notional is not None and self.target_fraction_of_equity is not None:
            raise ValueError(
                "SizingPolicy invalide : target_notional et "
                "target_fraction_of_equity sont tous deux configures. "
                "Exactement une base de sizing doit etre choisie."
            )

    @property
    def has_sizing_base(self) -> bool:
        return self.target_notional is not None or self.target_fraction_of_equity is not None

    @property
    def has_valid_quantity_increment(self) -> bool:
        return self.quantity_increment is not None and self.quantity_increment > 0
