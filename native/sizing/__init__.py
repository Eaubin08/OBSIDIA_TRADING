"""
Native Reference Sizing (P1-C).

Sizing n'invente aucune politique financiere/risque. Elle repond
uniquement : etant donne une SizingPolicy explicite et l'etat reel du
portefeuille, quelle quantite ce StrategyCandidate peut-il proposer ?

Sizing != Strategy, Sizing != KX108, Sizing != Binder, Sizing != Broker.
"""
from native.sizing.sizing_policy import SizingPolicy
from native.sizing.native_reference_sizing import NativeReferenceSizing

__all__ = ["SizingPolicy", "NativeReferenceSizing"]
