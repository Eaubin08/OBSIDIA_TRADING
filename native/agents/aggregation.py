"""
AggregationPort pour le roster natif (chantier F6).

Reduction pure d'un ensemble d'`AgentOutput` (signal BUY/SELL/HOLD + confiance)
en un `Consensus`. Aucune autorite ici : cette etape ne fait qu'agreger des
opinions, elle ne decide jamais ACT/HOLD/BLOCK — c'est le role exclusif de
`governance/bridge/` en aval.
"""
from __future__ import annotations

from typing import Sequence

from domain.proposal import AgentOutput, Consensus


class NativeRosterAggregation:
    """Agrege les votes du roster de 17 agents (execution/binder/contracts.py::AggregationPort)."""

    def aggregate(self, outputs: Sequence[AgentOutput]) -> Consensus:
        outputs = list(outputs)
        if not outputs:
            return Consensus(side="HOLD", confidence=0.0, uncertainty=1.0)

        buy_weight = sum(o.confidence for o in outputs if o.signal == "BUY")
        sell_weight = sum(o.confidence for o in outputs if o.signal == "SELL")
        hold_weight = sum(o.confidence for o in outputs if o.signal == "HOLD")
        total = buy_weight + sell_weight + hold_weight

        if total <= 0:
            side, confidence = "HOLD", 0.0
        elif buy_weight >= sell_weight and buy_weight >= hold_weight:
            side, confidence = "BUY", buy_weight / total
        elif sell_weight >= buy_weight and sell_weight >= hold_weight:
            side, confidence = "SELL", sell_weight / total
        else:
            side, confidence = "HOLD", hold_weight / total

        active = [o for o in outputs]
        agreement = (
            sum(1 for o in active if o.signal == side) / len(active) if active else None
        )
        opposing = tuple(
            f"{o.name}:{o.signal}:{o.confidence:.3f}"
            for o in active
            if o.signal not in (side, "HOLD")
        )
        provenance = tuple(f"{o.name}:{o.category}" for o in active)

        return Consensus(
            side=side,
            confidence=confidence,
            buy_weight=buy_weight,
            sell_weight=sell_weight,
            hold_weight=hold_weight,
            agreement_ratio=round(agreement, 6) if agreement is not None else None,
            opposing_evidence=opposing,
            uncertainty=round(1.0 - confidence, 6),
            agent_provenance=provenance,
        )
