"""
EXEMPLE PEDAGOGIQUE — external/examples/brother_stack/

CECI N'EST PAS UNE INTEGRATION REELLE. C'est une fixture illustrant comment
un futur adapter concret (ex: la stack Trading de mon frere, ou celle d'une
entreprise cliente) utiliserait `ExternalSignal` + `ExternalStackAdapter`
pour se brancher au meme pipeline de gouvernance que le chemin natif.

Aucun reseau, aucune donnee reelle, aucune dependance externe : les signaux
retournes sont codes en dur, uniquement pour demontrer la forme attendue.
"""
from __future__ import annotations

from typing import Sequence

from external.contracts.external_signal import ExternalSignal


class ExampleBrotherStackAdapter:
    """
    TEST / DEMO FIXTURE ONLY — n'est PAS une integration reelle (F15).

    Adapter d'exemple pour une stack Trading tierce fictive ("brother_strategy_07").
    Sert uniquement a exercer le contrat `ExternalTradingStackPort` /
    `ExternalSignal` avant qu'une vraie stack externe (celle du frere de
    l'utilisateur, ou une entreprise cliente) ne soit disponible. Ne
    represente le comportement d'aucune stack reelle. Un vrai adapter
    interrogerait ici l'API/le fichier/la base de la stack externe reelle ;
    celui-ci retourne un signal fixe, pour illustration uniquement.
    """

    adapter_id = "brother_stack_v1"
    organization_id = "brother_company"

    def fetch_signals(self, symbol: str) -> Sequence[ExternalSignal]:
        return [
            ExternalSignal.from_raw_payload(
                {
                    "source_id": "brother_strategy_07",
                    "organization_id": self.organization_id,
                    "adapter_id": self.adapter_id,
                    "symbol": symbol,
                    "signal": "BUY",
                    "confidence": 0.62,
                    "rationale": f"exemple pedagogique pour {symbol} — pas une vraie strategie",
                    "unknowns": ("stack_externe_non_auditee",),
                    "risk_flags": ("aucune_verification_independante",),
                },
                expected_symbol=symbol,
            )
        ]
