"""
F13.1 — Agents calibres : wrappers legers autour des agents natifs existants
(native/agents/domains/trading_agents.py, JAMAIS modifie ni reecrit ici).

Principe : le comportement par defaut de l'agent sous-jacent est preserve
a l'identique. La calibration n'intervient QUE dans les cas ou l'agent
sous-jacent serait de toute facon degrade (historique de prix trop court,
fallback arbitraire) ET seulement si le CalibrationPack est compatible
(meme symbole, statut calibre, pas perime). Sinon : comportement inchange
+ trace explicite de la raison (evidence_refs / unknowns), jamais une
substitution silencieuse.

Ce module n'importe rien depuis governance/ ni execution/binder/.
"""
from __future__ import annotations

from typing import Optional

from domain.calibration import CalibrationPack
from domain.calibration_consumption import (
    CompatibilityStatus,
    calibrated_daily_volatility_fallback,
    check_compatibility,
    evidence_refs_for_pack,
    garch_calibration_note,
    markov_calibration_note,
)
from native.agents.contracts import AgentVote
from native.agents.domains.trading_agents import RegimeShiftAgent, VolatilityAgent
from native.agents.utils.indicators import realized_volatility


class CalibrationAwareVolatilityAgent(VolatilityAgent):
    """
    Identique a VolatilityAgent sauf : si rv60 est degrade (moins de 60 prix
    disponibles, donc rv60 serait un fallback arbitraire cote agent
    d'origine) ET qu'un CalibrationPack compatible (meme symbole) fournit
    une volatilite journaliere calibree reelle, cette valeur remplace le
    fallback arbitraire pour le calcul de rv60 uniquement -- le seuil de
    decision (1.3x / 0.85x) de l'agent d'origine n'est jamais modifie.
    """

    agent_id = "VolatilityAgent"

    def __init__(self, calibration_pack: Optional[CalibrationPack] = None) -> None:
        self._pack = calibration_pack

    def evaluate(self, state) -> AgentVote:
        vote = super().evaluate(state)

        symbol = getattr(state, "symbol", "") or ""
        check = check_compatibility(self._pack, symbol)

        prices = list(getattr(state, "prices", []) or [])
        rv60_degraded = len(prices) < 61  # realized_volatility(prices, 60) exige 61 points

        if check.usable:
            # Evidence GARCH pure, jamais decisionnelle : attachee independamment
            # de rv60_degraded, comme la note Markov sur RegimeShift.
            garch_note = garch_calibration_note(self._pack)
            if garch_note:
                vote.evidence_refs = list(vote.evidence_refs) + evidence_refs_for_pack(self._pack) + [garch_note]

        if not rv60_degraded:
            return vote  # calcul local deja fiable : rien d'autre a faire

        if not check.usable:
            if self._pack is not None and check.status is not CompatibilityStatus.NO_PACK:
                vote.unknowns = list(vote.unknowns) + [f"CALIBRATION_UNAVAILABLE:{check.status.value}"]
            return vote

        calibrated_rv60 = calibrated_daily_volatility_fallback(self._pack)
        if calibrated_rv60 is None or calibrated_rv60 <= 0:
            return vote

        rv20 = realized_volatility(prices, 20) or 0.0
        verdict = (
            "SELL" if rv20 > calibrated_rv60 * 1.3
            else "BUY" if rv20 < calibrated_rv60 * 0.85
            else "HOLD"
        )
        conf = min(1.0, abs(rv20 / calibrated_rv60 - 1.0) * 2)

        vote.proposed_verdict = verdict
        vote.vote = verdict
        vote.confidence = conf
        vote.claim = f"rv20={rv20:.4f}, rv60_calibrated={calibrated_rv60:.4f} (source: {self._pack.calibration_id})"
        # evidence_refs deja enrichi de la provenance du pack ci-dessus (bloc check.usable).
        vote.risk_flags = list(vote.risk_flags) + (["HIGH_VOLATILITY"] if verdict == "SELL" else [])
        return vote


class CalibrationAwareRegimeShiftAgent(RegimeShiftAgent):
    """
    Identique a RegimeShiftAgent : le verdict n'est jamais recalcule a
    partir de la matrice Markov calibree (integrer une matrice de regimes
    dans la logique de decision serait une reecriture de l'agent, hors
    scope F13.1). Seule addition : si un CalibrationPack compatible existe,
    une note d'evidence sur l'etat de calibration Markov est attachee au
    vote, tracable jusqu'au receipt -- sans jamais influencer le verdict.
    """

    agent_id = "RegimeShiftAgent"

    def __init__(self, calibration_pack: Optional[CalibrationPack] = None) -> None:
        self._pack = calibration_pack

    def evaluate(self, state) -> AgentVote:
        vote = super().evaluate(state)

        symbol = getattr(state, "symbol", "") or ""
        check = check_compatibility(self._pack, symbol)

        if not check.usable:
            if self._pack is not None and check.status is not CompatibilityStatus.NO_PACK:
                vote.unknowns = list(vote.unknowns) + [f"CALIBRATION_UNAVAILABLE:{check.status.value}"]
            return vote

        note = markov_calibration_note(self._pack)
        if note:
            vote.evidence_refs = list(vote.evidence_refs) + evidence_refs_for_pack(self._pack) + [note]
        return vote


def build_calibrated_trading_agents(
    calibration_pack: Optional[CalibrationPack] = None,
) -> list:
    """
    Meme roster que native.agents.domains.trading_agents.build_trading_agents(),
    avec Volatility et RegimeShift remplaces par leurs variantes conscientes
    de la calibration. Les 15 autres agents sont strictement inchanges --
    ils n'ont aujourd'hui aucune donnee reelle calibree qui les concerne
    (spread/volume/macro/event/sentiment/portfolio ne sont pas couverts par
    le CalibrationPack F13, qui ne porte que sur les rendements de prix).
    """
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
        SentimentAgent,
    )

    return [
        MarketDataAgent(),
        LiquidityAgent(),
        CalibrationAwareVolatilityAgent(calibration_pack),
        MacroAgent(),
        CorrelationAgent(),
        EventAgent(),
        MomentumAgent(),
        MeanReversionAgent(),
        BreakoutAgent(),
        PatternAgent(),
        SentimentAgent(),
        PredictionAgent(),
        PortfolioAgent(),
        ExecutionQualityAgent(),
        CalibrationAwareRegimeShiftAgent(calibration_pack),
        PortfolioStressAgent(),
        ProofConsistencyAgent(),
    ]
