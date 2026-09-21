"""
Obsidia Trading — couches SIGNAL / OPPORTUNITE / STRATEGIE / PROPOSITION.

Chantier §8 : ne jamais confondre SIGNAL, PROPOSAL, DECISION et EXECUTION.
Le prototype les fusionnait — le consensus des agents ETAIT l'ordre. Ici :

    AgentOutput       un instrument observe et se prononce      (signal)
    Opportunity       une situation merite l'attention          (candidat)
    StrategyCandidate une maniere concrete d'y repondre         (plan de jeu)
    ActionProposal    ce que le systeme soumet a X-108          (proposition)

Aucune de ces couches n'a d'autorite. Elles alimentent la decision, elles ne
la prennent pas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from domain.types import ActionKind, OrderType, Side

# F3.5 - Canonical Domain Contract : ces quatre champs sont les invariants
# semantiques qu'un agent peut porter et qui ne doivent JAMAIS disparaitre
# silencieusement entre l'agent et le receipt final. Voir domain/contracts/.
CanonicalEvidence = Tuple[str, ...]


OPPORTUNITY_STATUSES = {"VALID", "WEAK", "CONFLICTED", "DEGRADED"}
SIZING_STATUSES = {"VALID", "REDUCED", "ZERO", "REJECTED"}
STRATEGY_STATUSES = {"VALID", "WEAK", "CONFLICTED", "INCOMPATIBLE"}


@dataclass(frozen=True)
class AgentOutput:
    """
    Sortie normalisee d'un agent d'analyse.

    Transpose `AgentVote` du prototype en y ajoutant `inputs_digest`, qui
    permet a un receipt de dire sur quoi l'agent s'est appuye, et non
    seulement ce qu'il a conclu.

    F3.5 (Canonical Domain Contract) : `unknowns`, `contradictions` et
    `risk_flags` sont des champs de PREMIERE CLASSE, pas des entrees
    optionnelles d'un blob libre. Un agent qui produit un unknown, une
    contradiction ou un risk_flag doit le retrouver ici, sous ce nom exact,
    jusqu'au receipt final (domain/receipt.py -> Decision -> ActionProposal
    -> AgentOutput). `inputs_digest` reste reserve aux metadonnees
    operationnelles non critiques (vote brut, layer, severity_hint) : rien
    de semantiquement important ne doit y etre range en exclusivite, car un
    "digest" peut legitimement etre resume/hashe plus tard sans que ce soit
    une regression.
    """

    name: str
    category: str
    signal: str
    confidence: float
    rationale: str
    unknowns: CanonicalEvidence = field(default_factory=tuple)
    contradictions: CanonicalEvidence = field(default_factory=tuple)
    risk_flags: CanonicalEvidence = field(default_factory=tuple)
    evidence_refs: CanonicalEvidence = field(default_factory=tuple)
    inputs_digest: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "agent": self.name,
            "category": self.category,
            "signal": self.signal,
            "confidence": round(self.confidence, 6),
            "rationale": self.rationale,
            "unknowns": list(self.unknowns),
            "contradictions": list(self.contradictions),
            "risk_flags": list(self.risk_flags),
            "evidence_refs": list(self.evidence_refs),
            "inputs": self.inputs_digest,
        }


@dataclass(frozen=True)
class Consensus:
    """Resultat de l'agregation des sorties d'agents."""

    side: str
    confidence: float
    buy_weight: float = 0.0
    sell_weight: float = 0.0
    hold_weight: float = 0.0
    agreement_ratio: Optional[float] = None
    opposing_evidence: Tuple[str, ...] = field(default_factory=tuple)
    uncertainty: float = 0.0
    degraded_inputs: Tuple[str, ...] = field(default_factory=tuple)
    agent_provenance: Tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {
            "side": self.side,
            "confidence": round(self.confidence, 6),
            "buy_weight": round(self.buy_weight, 6),
            "sell_weight": round(self.sell_weight, 6),
            "hold_weight": round(self.hold_weight, 6),
            "agreement_ratio": self.agreement_ratio,
            "opposing_evidence": list(self.opposing_evidence),
            "uncertainty": round(self.uncertainty, 6),
            "degraded_inputs": list(self.degraded_inputs),
            "agent_provenance": list(self.agent_provenance),
        }


@dataclass(frozen=True)
class Opportunity:
    """
    Situation jugee digne d'attention (chantier §6).

    Une opportunite n'est pas une intention de trade : c'est le constat qu'un
    instrument merite d'etre approfondi. Elle peut tout aussi bien porter sur
    une position existante a surveiller que sur une entree potentielle.
    """

    symbol: str
    score: float
    kind: str
    rationale: str
    metrics: Dict[str, float] = field(default_factory=dict)
    opportunity_id: str = ""
    directional_bias: Optional[str] = None
    source: str = "unknown"
    confidence: float = 0.0
    strength: float = 0.0
    timeframe: str = "cycle"
    market_context: Dict[str, Any] = field(default_factory=dict)
    supporting_signals: Tuple[str, ...] = field(default_factory=tuple)
    opposing_signals: Tuple[str, ...] = field(default_factory=tuple)
    risk_context: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)
    status: str = "VALID"

    def __post_init__(self) -> None:
        if self.status not in OPPORTUNITY_STATUSES:
            raise ValueError(f"unknown opportunity status: {self.status}")
        if not self.opportunity_id:
            bias = self.directional_bias or "attention"
            object.__setattr__(
                self,
                "opportunity_id",
                f"opp:{self.symbol}:{self.kind}:{bias}",
            )
        if self.confidence == 0.0:
            object.__setattr__(self, "confidence", self.score)
        if self.strength == 0.0:
            object.__setattr__(self, "strength", self.score)

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "score": round(self.score, 6),
            "kind": self.kind,
            "rationale": self.rationale,
            "metrics": {k: round(v, 6) for k, v in self.metrics.items()},
            "opportunity_id": self.opportunity_id,
            "directional_bias": self.directional_bias,
            "source": self.source,
            "confidence": round(self.confidence, 6),
            "strength": round(self.strength, 6),
            "timeframe": self.timeframe,
            "market_context": self.market_context,
            "supporting_signals": list(self.supporting_signals),
            "opposing_signals": list(self.opposing_signals),
            "risk_context": self.risk_context,
            "provenance": self.provenance,
            "status": self.status,
        }


@dataclass(frozen=True)
class StrategyCandidate:
    """
    Une maniere concrete de repondre a une opportunite (chantier §9).

    Porte l'ensemble de ce qui rend une strategie comparable a une autre :
    entree, sortie, invalidation, horizon, risque. Plusieurs candidates
    peuvent coexister pour un meme symbole et etre departagees.
    """

    symbol: str
    action: ActionKind
    rationale: str
    confidence: float
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    horizon_s: Optional[float] = None
    invalidation: str = ""
    expected_risk: Optional[float] = None
    order_type: OrderType = OrderType.MARKET
    provenance: str = ""
    strategy_id: str = ""
    opportunity_id: str = ""
    constraints: Tuple[str, ...] = field(default_factory=tuple)
    required_conditions: Tuple[str, ...] = field(default_factory=tuple)
    supporting_evidence: Tuple[str, ...] = field(default_factory=tuple)
    opposing_evidence: Tuple[str, ...] = field(default_factory=tuple)
    status: str = "VALID"

    def __post_init__(self) -> None:
        if self.status not in STRATEGY_STATUSES:
            raise ValueError(f"unknown strategy status: {self.status}")
        if not self.strategy_id:
            object.__setattr__(
                self,
                "strategy_id",
                f"strat:{self.symbol}:{self.action.value}:{self.provenance or 'strategy'}",
            )

    @property
    def side(self) -> Optional[Side]:
        return self.action.side

    @property
    def risk_reward(self) -> Optional[float]:
        """Ratio gain vise / perte acceptee, quand les deux sont definis."""
        if self.entry_price is None or self.stop_loss is None or self.take_profit is None:
            return None
        risk = abs(self.entry_price - self.stop_loss)
        if risk <= 0:
            return None
        return abs(self.take_profit - self.entry_price) / risk

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "action": self.action.value,
            "side": self.side.value if self.side else None,
            "rationale": self.rationale,
            "confidence": round(self.confidence, 6),
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "risk_reward": self.risk_reward,
            "horizon_s": self.horizon_s,
            "invalidation": self.invalidation,
            "expected_risk": self.expected_risk,
            "order_type": self.order_type.value,
            "provenance": self.provenance,
            "strategy_id": self.strategy_id,
            "opportunity_id": self.opportunity_id,
            "constraints": list(self.constraints),
            "required_conditions": list(self.required_conditions),
            "supporting_evidence": list(self.supporting_evidence),
            "opposing_evidence": list(self.opposing_evidence),
            "status": self.status,
        }


@dataclass(frozen=True)
class SizingDecision:
    """
    Resultat de la couche de dimensionnement (chantier §11).

    Volontairement distincte de la direction : le systeme doit pouvoir
    reduire ou refuser une taille sans changer d'avis sur le sens. `capped_by`
    nomme la contrainte qui a mordu, ce qui rend le refus explicable.
    """

    quantity: float
    requested_quantity: float
    capped_by: Tuple[str, ...] = field(default_factory=tuple)
    notional: Optional[float] = None
    rationale: str = ""
    fraction: Optional[float] = None
    exposure_after: Optional[float] = None
    constraints: Tuple[str, ...] = field(default_factory=tuple)
    status: str = ""

    def __post_init__(self) -> None:
        if not self.status:
            if self.quantity <= 0 and self.requested_quantity <= 0:
                status = "ZERO"
            elif self.quantity <= 0:
                status = "REJECTED"
            elif self.quantity < self.requested_quantity:
                status = "REDUCED"
            else:
                status = "VALID"
            object.__setattr__(self, "status", status)
        elif self.status not in SIZING_STATUSES:
            raise ValueError(f"unknown sizing status: {self.status}")

    @property
    def was_reduced(self) -> bool:
        return self.quantity < self.requested_quantity

    @property
    def is_refused(self) -> bool:
        return self.quantity <= 0

    def as_dict(self) -> dict:
        return {
            "quantity": self.quantity,
            "requested_quantity": self.requested_quantity,
            "was_reduced": self.was_reduced,
            "is_refused": self.is_refused,
            "capped_by": list(self.capped_by),
            "notional": self.notional,
            "rationale": self.rationale,
            "fraction": self.fraction,
            "exposure_after": self.exposure_after,
            "constraints": list(self.constraints),
            "status": self.status,
        }


@dataclass(frozen=True)
class ActionProposal:
    """
    Ce que le systeme soumet a X-108.

    C'est le dernier objet produit AVANT toute autorite. Il agrege ce qui a
    ete observe, envisage, compare et dimensionne, mais ne prejuge de rien :
    X-108 reste libre de repondre ACT, HOLD ou BLOCK.
    """

    symbol: str
    action: ActionKind
    consensus: Consensus
    sizing: SizingDecision
    selected_strategy: Optional[StrategyCandidate] = None
    rejected_strategies: Tuple[StrategyCandidate, ...] = field(default_factory=tuple)
    agent_outputs: Tuple[AgentOutput, ...] = field(default_factory=tuple)
    opportunity: Optional[Opportunity] = None
    rationale: str = ""
    proposal_id: str = ""
    candidate_rank: int = 0
    portfolio_context: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.proposal_id:
            object.__setattr__(
                self,
                "proposal_id",
                f"proposal:{self.symbol}:{self.action.value}:{self.candidate_rank}",
            )

    @property
    def side(self) -> Optional[Side]:
        return self.action.side

    @property
    def requires_authority(self) -> bool:
        """Vrai si accepter cette proposition modifierait l'exterieur."""
        return self.action.is_irreversible

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "action": self.action.value,
            "side": self.side.value if self.side else None,
            "requires_authority": self.requires_authority,
            "consensus": self.consensus.as_dict(),
            "sizing": self.sizing.as_dict(),
            "selected_strategy": (
                self.selected_strategy.as_dict() if self.selected_strategy else None
            ),
            "rejected_strategies": [s.as_dict() for s in self.rejected_strategies],
            "agent_outputs": [a.as_dict() for a in self.agent_outputs],
            "opportunity": self.opportunity.as_dict() if self.opportunity else None,
            "rationale": self.rationale,
            "proposal_id": self.proposal_id,
            "candidate_rank": self.candidate_rank,
            "portfolio_context": self.portfolio_context,
        }
