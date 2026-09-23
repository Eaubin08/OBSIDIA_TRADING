"""
Obsidia Trading — point d'extension pour une stack externe concrete (F8).

`ExternalStackAdapter` est le Protocol qu'une future integration reelle
(ex: la stack de trading de mon frere, ou une entreprise cliente) doit
implementer. Il sait comment PARLER a la stack tierce (API/fichier/
websocket/base de donnees/etc.) et produit des `ExternalSignal` bruts.

`ExternalStackAnalysisAdapter` implemente `AnalysisPort`
(execution/binder/contracts.py) exactement comme `NativeRosterAnalysisAdapter`
(native/agents/adapter.py) : il peut etre branche dans `CycleEngine` a la
place du roster natif, sans aucune modification du moteur, du Governance
Bridge ou de KX108. C'est la preuve structurelle qu'aucune deuxieme
architecture metier n'est creee (chantier F8).
"""
from __future__ import annotations

from typing import List, Optional, Protocol, Sequence

from domain.market import MarketSnapshot
from domain.portfolio import PortfolioState
from domain.proposal import AgentOutput
from domain.provenance import SourceKind
from external.contracts.external_signal import ExternalSignal
from external.normalization.normalizer import normalize_external_signal


class ExternalStackAdapter(Protocol):
    """
    Implemente par une integration concrete (ex: external/examples/brother_stack/,
    ou une future vraie stack externe — voir docs/EXTERNAL_STACK_INTEGRATION_GUIDE.md).

    Ne vote jamais lui-meme, ne decide jamais, n'a jamais acces a
    Binder/Broker/Governance — seulement a la stack tierce qu'il interroge.
    """

    adapter_id: str
    organization_id: str

    def fetch_signals(self, symbol: str) -> Sequence[ExternalSignal]:
        ...


# F15 : nom stable pour ce contrat, destine a etre le point de reference
# documente pour une future integration reelle. `ExternalStackAdapter` reste
# l'alias historique (F8) — les deux designent le meme Protocol, ne jamais
# les faire diverger.
ExternalTradingStackPort = ExternalStackAdapter


class ExternalStackAnalysisAdapter:
    """
    Implemente `AnalysisPort` en deleguant a un `ExternalStackAdapter`.

    Ne fait rien d'autre que : interroger l'adapter concret, normaliser
    chaque `ExternalSignal` recu, et renvoyer les `AgentOutput` resultants.
    Aucune agregation, aucune decision, aucun acces broker.
    """

    def __init__(self, adapter: ExternalStackAdapter, *, source_kind: SourceKind = SourceKind.API) -> None:
        self._adapter = adapter
        self._source_kind = source_kind

    def analyse(
        self,
        symbol: str,
        snapshot: MarketSnapshot,
        portfolio: Optional[PortfolioState],
    ) -> Sequence[AgentOutput]:
        raw_signals = self._adapter.fetch_signals(symbol)
        outputs: List[AgentOutput] = []
        for signal in raw_signals:
            # F15 : defense en profondeur — meme si `fetch_signals` a deja
            # valide via `ExternalSignal.from_raw_payload(expected_symbol=...)`,
            # un adapter concret bugue pourrait renvoyer un symbole different
            # de celui demande. Un signal hors-symbole est REJETE ici, jamais
            # normalise silencieusement vers le mauvais marche.
            if signal.symbol != symbol:
                continue
            outputs.append(
                normalize_external_signal(
                    signal,
                    adapter_id=self._adapter.adapter_id,
                    source_kind=self._source_kind,
                )
            )
        return outputs
