"""
Adapter entre le roster natif de 17 agents (core Obsidia, sigma/domains/trading_agents.py)
et le moteur de cycle porte depuis agent-trad-main (execution/binder/engine.py).

Pourquoi un adapter et pas une fusion directe des deux vocabulaires :

Le moteur de cycle attend `AnalysisPort.analyse(...) -> Sequence[AgentOutput]`
(domain/proposal.py : name, category, signal, confidence, rationale, inputs_digest).

Le roster natif produit `AgentVote` (native/agents/contracts.py : agent_id, vote,
proposed_verdict, confidence, domain, layer, claim, contradictions, unknowns,
risk_flags, evidence_refs, severity_hint) — un format bien plus riche, avec
exactement les champs que l'architecture cible veut au niveau du futur
Canonical Domain Contract (unknowns, contradictions, risk_flags, evidence).

F3.5 (Canonical Domain Contract Closure) : `unknowns`/`contradictions`/
`risk_flags`/`evidence_refs` sont maintenant des champs de premiere classe sur
`AgentOutput` (domain/proposal.py), pas des entrees compressees dans
`inputs_digest`. Ce fichier est le SEUL point de traduction AgentVote ->
AgentOutput : voir domain/contracts/canonical.py pour la definition normative
du contrat et tests/unit/test_canonical_contract_integrity.py pour la preuve
de non-perte agent -> receipt.

Chaque agent recoit un `TradingState` (native/agents/contracts.py) reconstruit
depuis `MarketSnapshot.bars` (domain/market.py). Les champs sans equivalent dans
Bar (spreads_bps, sentiment_scores, event_risk_scores, btc_reference_prices)
restent vides plutot que d'etre invente — les agents qui en dependent
(LiquidityAgent, SentimentAgent, EventAgent) operent alors sur une donnee connue
comme incomplete. Ceci est un gap documente, pas un defaut cache.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from domain.contracts.canonical import to_canonical_agent_signal
from domain.market import MarketSnapshot
from domain.portfolio import PortfolioState
from domain.proposal import AgentOutput
from domain.provenance import SourceProvenance

from native.agents.contracts import AgentVote, TradingState
from native.agents.domains.trading_agents import (
    BreakoutAgent,
    CorrelationAgent,
    EventAgent,
    ExecutionQualityAgent,
    LiquidityAgent,
    MacroAgent,
    MarketDataAgent,
    MeanReversionAgent,
    MomentumAgent,
    PatternAgent,
    PortfolioAgent,
    PortfolioStressAgent,
    PredictionAgent,
    ProofConsistencyAgent,
    RegimeShiftAgent,
    SentimentAgent,
    VolatilityAgent,
)

ROSTER_17 = (
    MarketDataAgent,
    LiquidityAgent,
    VolatilityAgent,
    MacroAgent,
    CorrelationAgent,
    EventAgent,
    MomentumAgent,
    MeanReversionAgent,
    BreakoutAgent,
    PatternAgent,
    SentimentAgent,
    PredictionAgent,
    PortfolioAgent,
    ExecutionQualityAgent,
    RegimeShiftAgent,
    PortfolioStressAgent,
    ProofConsistencyAgent,
)


def trading_state_from_snapshot(symbol: str, snapshot: MarketSnapshot) -> TradingState:
    """Reconstruit un TradingState a partir des bars OHLCV connus du snapshot.

    Les champs sans equivalent dans Bar (spread, sentiment, event risk, BTC
    reference) restent a leur defaut (liste vide) : on ne les invente pas.
    """
    bars = snapshot.bars
    prices = [b.close for b in bars] if bars else [snapshot.last_price]
    highs = [b.high for b in bars] if bars else [snapshot.last_price]
    lows = [b.low for b in bars] if bars else [snapshot.last_price]
    volumes = [b.volume for b in bars] if bars else [snapshot.volume or 0.0]
    return TradingState(
        symbol=symbol,
        prices=prices,
        highs=highs,
        lows=lows,
        volumes=volumes,
    )


def agent_vote_to_agent_output(vote: AgentVote) -> AgentOutput:
    """Traduit un AgentVote (roster natif) vers AgentOutput (moteur de cycle).

    F3.5 : unknowns/contradictions/risk_flags/evidence_refs sont copies vers
    les champs de premiere classe d'AgentOutput — source de verite unique.
    `inputs_digest` ne porte plus que des metadonnees operationnelles
    (vote brut, layer, severity_hint) qui n'ont pas d'equivalent de premiere
    classe cote AgentOutput.

    F7.5 : `source_provenance` est attache automatiquement ici
    (`SourceProvenance.for_native_agent`) — c'est le SEUL endroit qui tague
    un signal comme natif. Aucune valeur par defaut dispersee ailleurs dans
    le code.

    F8.7 (Canonical Convergence Closure) : cette fonction appelle desormais
    `to_canonical_agent_signal` (domain/contracts/canonical.py) au lieu de
    construire `AgentOutput(...)` directement. C'est le MEME point de
    convergence que celui emprunte par le chemin externe
    (external/normalization/normalizer.py::normalize_external_signal).
    Audit prealable (F8.7) : `to_canonical_agent_signal` ne contenait deja
    aucune hypothese specifique au format ExternalSignal — ses parametres
    sont des primitives neutres (confidence/unknowns/contradictions/
    risk_flags/evidence_refs/operational_metadata/source_provenance), donc
    aucun refactor de la fonction elle-meme n'a ete necessaire (CAS A, pas
    CAS B) : seul cet appelant a change sa facon de construire le signal.
    """
    return to_canonical_agent_signal(
        agent_id=vote.agent_id,
        category=str(vote.domain),
        signal=vote.proposed_verdict,
        confidence=float(vote.confidence),
        rationale=vote.claim,
        unknowns=vote.unknowns,
        contradictions=vote.contradictions,
        risk_flags=vote.risk_flags,
        evidence_refs=vote.evidence_refs,
        operational_metadata={
            "vote": vote.vote,
            "layer": vote.layer,
            "severity_hint": str(vote.severity_hint),
        },
        source_provenance=SourceProvenance.for_native_agent(vote.agent_id),
    )


class NativeRosterAnalysisAdapter:
    """Implemente AnalysisPort (execution/binder/contracts.py) avec le roster de 17 agents.

    Ne decide jamais : produit des AgentOutput, rien de plus. L'agregation,
    la decision et l'execution restent hors de cette classe.
    """

    def __init__(self, agent_classes: Sequence[type] = ROSTER_17) -> None:
        self._agents = [cls() for cls in agent_classes]

    def analyse(
        self,
        symbol: str,
        snapshot: MarketSnapshot,
        portfolio: Optional[PortfolioState],
    ) -> Sequence[AgentOutput]:
        state = trading_state_from_snapshot(symbol, snapshot)
        outputs: List[AgentOutput] = []
        for agent in self._agents:
            vote = agent.evaluate(state)
            outputs.append(agent_vote_to_agent_output(vote))
        return outputs
