"""
Obsidia Trading — port preuve (chantier §23).

Le moteur emet un receipt par cycle, quelle que soit l'autorite. Il ignore ou
et comment celui-ci est conserve : fichier JSON comme aujourd'hui, base,
registre ERC-8004, ou plusieurs a la fois.

La responsabilite du chainage appartient a l'implementation : c'est elle qui
connait le dernier hash emis et peut donc garantir la continuite de la chaine
d'un cycle a l'autre.
"""
from __future__ import annotations

from typing import Optional, Protocol, Sequence, runtime_checkable

from domain.receipt import CycleReceipt


@runtime_checkable
class ProofPort(Protocol):
    """Conservation et relecture des preuves de cycle."""

    def last_hash(self) -> str:
        """
        Hash du dernier receipt conserve, ou GENESIS_HASH si le journal est
        vide. Sert a chainer le receipt suivant.
        """
        ...

    def record(self, receipt: CycleReceipt) -> CycleReceipt:
        """
        Conserve un receipt et retourne CELUI QUI A ETE CONSERVE.

        Une implementation peut enrichir le receipt avant stockage — c'est le
        cas de l'extension ERC-8004. Retourner la version conservee garantit
        que l'appelant voit exactement ce qui a ete prouve, et que le hash de
        chainage porte sur le bon contenu.
        """
        ...

    def read(self, decision_id: str) -> Optional[CycleReceipt]:
        """Relit un receipt par son identifiant de decision."""
        ...

    def history(self, limit: int = 100) -> Sequence[CycleReceipt]:
        """Receipts les plus recents, du plus ancien au plus recent."""
        ...
