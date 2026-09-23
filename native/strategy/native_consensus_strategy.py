"""
Obsidia Trading — Native Reference Strategy (P1-B).

Transcrit honnetement le Consensus produit par l'agregation des 17 agents
Native en StrategyCandidate(s). Ne decide jamais ACT/HOLD/BLOCK, ne
dimensionne jamais de position, n'appelle jamais KX108/Binder/Broker.

CycleEngine (execution/binder/engine.py::_action_from) applique deja ce meme
repli — BUY/SELL transcrits directement depuis Consensus.side, tout le reste
(HOLD compris) => ActionKind.WAIT — quand aucune Strategy n'est fournie.
Cette classe rend ce comportement explicite, tracable et pourvu de
statut/evidence, plutot que de laisser un repli implicite du moteur.

Ne pas confondre avec Sizing (P1-C) ou la gouvernance en aval : cette
Strategy n'utilise jamais gross_exposure/net_exposure/drawdown/concentration/
buying_power du portefeuille pour rejeter ou changer une direction. Aucune
regle semantique existante ne le justifierait aujourd'hui — ce choix
appartient au Sizing/a la gouvernance, pas a la Strategy.

Strategy != Authority. Strategy != Sizing. Strategy != Execution.
"""
from __future__ import annotations

from typing import Optional, Sequence

from domain.market import MarketSnapshot
from domain.portfolio import PortfolioState
from domain.proposal import Consensus, Opportunity, StrategyCandidate
from domain.types import ActionKind

PROVENANCE = "native_reference_strategy.v1"

_DIRECTION = {
    "BUY": ActionKind.BUY,
    "SELL": ActionKind.SELL,
}


class NativeReferenceStrategy:
    """
    Strategy de reference V1 : transcrit le Consensus Native, n'invente rien.

    entry_price/stop_loss/take_profit/horizon_s/expected_risk restent
    explicitement absents (None) — aucune source canonique de ce repo ne
    definit de niveau d'entree, de politique de sortie ou d'horizon ; les
    inventer serait fabriquer une donnee (voir P1-B, docs/MIGRATION_PROVENANCE.md).
    """

    def build(
        self,
        symbol: str,
        snapshot: MarketSnapshot,
        consensus: Consensus,
        portfolio: Optional[PortfolioState],
        opportunities: Sequence[Opportunity] = (),
    ) -> Sequence[StrategyCandidate]:
        action = _DIRECTION.get(consensus.side)
        if action is None:
            # HOLD, ou tout side inconnu/absent : jamais de candidate
            # directionnelle. Ne devine jamais une direction.
            return ()

        # Meme filtre deterministe que CycleEngine._select_symbol utilise
        # deja ailleurs pour rattacher une Opportunity a un symbole
        # (execution/binder/engine.py) — aucune logique de ranking nouvelle.
        opportunity = next((o for o in opportunities if o.symbol == symbol), None)
        status = self._status(consensus, opportunity)

        return (
            StrategyCandidate(
                symbol=symbol,
                action=action,
                rationale=(
                    "Transcription directe du Consensus Native "
                    f"(side={consensus.side}, confidence={consensus.confidence:.4f})."
                ),
                confidence=consensus.confidence,
                opposing_evidence=consensus.opposing_evidence,
                provenance=PROVENANCE,
                opportunity_id=opportunity.opportunity_id if opportunity else "",
                status=status,
            ),
        )

    @staticmethod
    def _status(consensus: Consensus, opportunity: Optional[Opportunity]) -> str:
        """
        CONFLICTED > WEAK > VALID. Derive uniquement d'evidence semantique
        deja portee par Consensus/Opportunity — jamais d'un seuil numerique
        arbitraire sur agreement_ratio/confidence/buy_weight/sell_weight/
        uncertainty.
        """
        conflicted = bool(consensus.opposing_evidence) or (
            opportunity is not None and opportunity.status == "CONFLICTED"
        )
        if conflicted:
            return "CONFLICTED"

        weak = bool(consensus.degraded_inputs) or (
            opportunity is not None and opportunity.status in ("WEAK", "DEGRADED")
        )
        if weak:
            return "WEAK"

        return "VALID"
