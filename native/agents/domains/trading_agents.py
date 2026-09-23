from __future__ import annotations

from typing import List

from ..base import BaseAgent
from ..contracts import AgentVote, Domain, Layer, Severity, TradingState
from ..utils.indicators import rsi, zscore, bollinger, realized_volatility


def _ret(values: List[float], n: int = 1) -> float:
    if len(values) < n + 1 or values[-n - 1] == 0:
        return 0.0
    return (values[-1] - values[-n - 1]) / values[-n - 1]


class MarketDataAgent(BaseAgent):
    agent_id = "MarketDataAgent"
    def evaluate(self, state: TradingState) -> AgentVote:
        change = _ret(state.prices, 1)
        verdict = "BUY" if change > 0.001 else "SELL" if change < -0.001 else "HOLD"
        return AgentVote(self.agent_id, Domain.TRADING, Layer.OBSERVATION, f"1-step return={change:.4f}", min(1.0, abs(change)*25), Severity.S1, proposed_verdict=verdict)


class LiquidityAgent(BaseAgent):
    agent_id = "LiquidityAgent"
    def evaluate(self, state: TradingState) -> AgentVote:
        avg_vol = sum(state.volumes[-20:]) / max(1, min(len(state.volumes),20))
        spread = state.spreads_bps[-1] if state.spreads_bps else None
        # P1-A : un spread inconnu n'est jamais lu comme "serre" (favorable).
        # UNKNOWN != ZERO.
        if spread is None:
            return AgentVote(self.agent_id, Domain.TRADING, Layer.OBSERVATION, f"spread inconnu, avg_vol={avg_vol:.2f}", 0.3, Severity.S1, proposed_verdict="HOLD", unknowns=["MISSING_SPREAD"])
        liquid = avg_vol > 0 and state.volumes[-1] >= avg_vol and spread < 12
        verdict = "BUY" if liquid else "SELL" if spread > 25 else "HOLD"
        return AgentVote(self.agent_id, Domain.TRADING, Layer.OBSERVATION, f"spread_bps={spread:.2f}, avg_vol={avg_vol:.2f}", 0.7 if liquid else 0.5, Severity.S1, proposed_verdict=verdict)


class VolatilityAgent(BaseAgent):
    agent_id = "VolatilityAgent"
    def evaluate(self, state: TradingState) -> AgentVote:
        rv20 = realized_volatility(state.prices, 20) or 0.0
        rv60 = realized_volatility(state.prices, 60) or rv20 or 0.0001
        verdict = "SELL" if rv20 > rv60 * 1.3 else "BUY" if rv20 < rv60 * 0.85 else "HOLD"
        conf = min(1.0, abs(rv20/rv60-1.0)*2) if rv60 else 0.2
        return AgentVote(self.agent_id, Domain.TRADING, Layer.OBSERVATION, f"rv20={rv20:.4f}, rv60={rv60:.4f}", conf, Severity.S2 if verdict=="SELL" else Severity.S1, proposed_verdict=verdict, risk_flags=["HIGH_VOLATILITY"] if verdict=="SELL" else [])


class MacroAgent(BaseAgent):
    agent_id = "MacroAgent"
    def evaluate(self, state: TradingState) -> AgentVote:
        # P1-A : aucun fournisseur macro/event reel n'existe dans le repo.
        # Le neutre 0.5 (confiance 0.0, verdict HOLD) etait deja honnete
        # numeriquement ; on ajoute l'unknown explicite pour l'auditabilite.
        if not state.event_risk_scores:
            return AgentVote(self.agent_id, Domain.TRADING, Layer.OBSERVATION, "event_risk inconnu", 0.0, Severity.S1, proposed_verdict="HOLD", unknowns=["MISSING_EVENT_RISK"])
        risk = state.event_risk_scores[-1]
        verdict = "SELL" if risk > 0.7 else "BUY" if risk < 0.3 else "HOLD"
        return AgentVote(self.agent_id, Domain.TRADING, Layer.OBSERVATION, f"event_risk={risk:.2f}", min(1.0, abs(risk-0.5)*2), Severity.S2 if risk > 0.7 else Severity.S1, proposed_verdict=verdict)


class CorrelationAgent(BaseAgent):
    agent_id = "CorrelationAgent"
    def evaluate(self, state: TradingState) -> AgentVote:
        # P1-A : aucune reference BTC reelle n'existe -- deja neutre
        # numeriquement (verdict HOLD garanti si btc_reference_prices est
        # vide), unknown ajoute pour l'auditabilite.
        if not state.btc_reference_prices:
            asset_ret = _ret(state.prices, 5)
            return AgentVote(self.agent_id, Domain.TRADING, Layer.OBSERVATION, f"asset_ret={asset_ret:.4f}, ref inconnue", 0.0, Severity.S1, proposed_verdict="HOLD", unknowns=["MISSING_BTC_REFERENCE"])
        asset_ret = _ret(state.prices, 5)
        ref_ret = _ret(state.btc_reference_prices, 5)
        verdict = "BUY" if asset_ret > 0 and ref_ret > 0 else "SELL" if asset_ret < 0 and ref_ret < 0 else "HOLD"
        conf = min(1.0, abs(asset_ret - ref_ret) * 10)
        return AgentVote(self.agent_id, Domain.TRADING, Layer.OBSERVATION, f"asset_ret={asset_ret:.4f}, ref_ret={ref_ret:.4f}", conf, Severity.S1, proposed_verdict=verdict)


class EventAgent(BaseAgent):
    agent_id = "EventAgent"
    def evaluate(self, state: TradingState) -> AgentVote:
        # P1-A : le defaut 0.0 tombait sous le seuil BUY (risk<0.25) --
        # "pas de donnee event" se lisait comme "signal event haussier
        # confirme". UNKNOWN != ZERO : HOLD explicite a la place.
        if not state.event_risk_scores:
            return AgentVote(self.agent_id, Domain.TRADING, Layer.OBSERVATION, "event_shock inconnu", 0.0, Severity.S1, proposed_verdict="HOLD", unknowns=["MISSING_EVENT_RISK"])
        risk = state.event_risk_scores[-1]
        verdict = "SELL" if risk > 0.65 else "BUY" if risk < 0.25 else "HOLD"
        return AgentVote(self.agent_id, Domain.TRADING, Layer.OBSERVATION, f"event_shock={risk:.2f}", min(1.0, abs(risk-0.45)*1.8), Severity.S2 if risk > 0.65 else Severity.S1, proposed_verdict=verdict)


class MomentumAgent(BaseAgent):
    agent_id = "MomentumAgent"
    def evaluate(self, state: TradingState) -> AgentVote:
        ret5 = _ret(state.prices, 5)
        r = rsi(state.prices, 14)
        verdict = "BUY" if ret5 > 0 and (r is None or r < 75) else "SELL" if ret5 < 0 and (r is None or r > 25) else "HOLD"
        return AgentVote(self.agent_id, Domain.TRADING, Layer.INTERPRETATION, f"ret5={ret5:.4f}, rsi14={r}", min(1.0, abs(ret5)*20), Severity.S1, proposed_verdict=verdict)


class MeanReversionAgent(BaseAgent):
    agent_id = "MeanReversionAgent"
    def evaluate(self, state: TradingState) -> AgentVote:
        z = zscore(state.prices, 20)
        lower, _, upper = bollinger(state.prices, 20, 2.0)
        if z is None or lower is None or upper is None:
            return AgentVote(self.agent_id, Domain.TRADING, Layer.INTERPRETATION, "need 20 prices", 0.2, Severity.S1)
        px = state.prices[-1]
        verdict = "BUY" if px < lower or z < -2.0 else "SELL" if px > upper or z > 2.0 else "HOLD"
        return AgentVote(self.agent_id, Domain.TRADING, Layer.INTERPRETATION, f"zscore20={z:.2f}", min(1.0, abs(z)/3), Severity.S1, proposed_verdict=verdict)


class BreakoutAgent(BaseAgent):
    agent_id = "BreakoutAgent"
    def evaluate(self, state: TradingState) -> AgentVote:
        if len(state.highs) < 20 or len(state.lows) < 20:
            return AgentVote(self.agent_id, Domain.TRADING, Layer.INTERPRETATION, "need 20 highs/lows", 0.2, Severity.S1)
        last = state.prices[-1]
        resistance = max(state.highs[-20:])
        support = min(state.lows[-20:])
        verdict = "BUY" if last > resistance else "SELL" if last < support else "HOLD"
        distance = max(abs(last - resistance), abs(last - support)) / max(last, 1e-9)
        return AgentVote(self.agent_id, Domain.TRADING, Layer.INTERPRETATION, f"support={support:.2f}, resistance={resistance:.2f}", min(1.0, distance*25), Severity.S1, proposed_verdict=verdict)


class PatternAgent(BaseAgent):
    agent_id = "PatternAgent"
    def evaluate(self, state: TradingState) -> AgentVote:
        seq = state.prices[-5:]
        if len(seq) < 5:
            return AgentVote(self.agent_id, Domain.TRADING, Layer.INTERPRETATION, "need 5 prices", 0.2, Severity.S1)
        rises = sum(1 for i in range(1, len(seq)) if seq[i] > seq[i-1])
        drops = sum(1 for i in range(1, len(seq)) if seq[i] < seq[i-1])
        verdict = "BUY" if rises >= 4 else "SELL" if drops >= 4 else "HOLD"
        return AgentVote(self.agent_id, Domain.TRADING, Layer.INTERPRETATION, f"up_moves={rises}, down_moves={drops}", min(1.0, max(rises,drops)/5), Severity.S1, proposed_verdict=verdict)


class SentimentAgent(BaseAgent):
    agent_id = "SentimentAgent"
    def evaluate(self, state: TradingState) -> AgentVote:
        # P1-A : aucune source de sentiment reelle n'existe -- deja neutre
        # numeriquement (score 0.0 -> HOLD, confiance 0.0), unknown ajoute.
        if not state.sentiment_scores:
            return AgentVote(self.agent_id, Domain.TRADING, Layer.INTERPRETATION, "sentiment inconnu", 0.0, Severity.S1, proposed_verdict="HOLD", unknowns=["MISSING_SENTIMENT"])
        score = state.sentiment_scores[-1]
        verdict = "BUY" if score > 0.2 else "SELL" if score < -0.2 else "HOLD"
        return AgentVote(self.agent_id, Domain.TRADING, Layer.INTERPRETATION, f"sentiment={score:.2f}", min(1.0, abs(score)), Severity.S1, proposed_verdict=verdict)


class PredictionAgent(BaseAgent):
    agent_id = "PredictionAgent"
    def evaluate(self, state: TradingState) -> AgentVote:
        # P1-A : rv20 reste calcule sur les vrais prix (inchange). risk/
        # spread manquants ne sont plus substitues par 0.0 dans la formule
        # (ce qui abaissait artificiellement le composite vers le seuil
        # BUY<0.35) -- ils sont simplement omis du composite et signales.
        rv20 = realized_volatility(state.prices, 20) or 0.0
        unknowns = []
        composite = rv20 * 10
        if state.event_risk_scores:
            composite += state.event_risk_scores[-1] * 0.7
        else:
            unknowns.append("MISSING_EVENT_RISK")
        if state.spreads_bps:
            composite += state.spreads_bps[-1] / 100
        else:
            unknowns.append("MISSING_SPREAD")
        composite = min(1.0, composite)
        verdict = "SELL" if composite > 0.70 else "BUY" if composite < 0.35 else "HOLD"
        return AgentVote(self.agent_id, Domain.TRADING, Layer.INTERPRETATION, f"composite_risk={composite:.2f}", min(1.0, abs(composite-0.5)*2), Severity.S2 if composite > 0.70 else Severity.S1, proposed_verdict=verdict, unknowns=unknowns)


class PortfolioAgent(BaseAgent):
    agent_id = "PortfolioAgent"
    def evaluate(self, state: TradingState) -> AgentVote:
        # P1-A : c'etait le cas le plus grave -- exposure/drawdown a 0.0
        # (fallback dynamique) se lisait comme "portefeuille sans risque"
        # et produisait un BUY fabrique (0.0<0.30 et 0.0<0.03). Un
        # portefeuille reel non fourni doit produire HOLD + unknown, jamais
        # une confiance directionnelle.
        unknowns = []
        if state.drawdown is None:
            unknowns.append("MISSING_PORTFOLIO_STATE")
        if state.exposure is None:
            unknowns.append("EXPOSURE_SEMANTICS_UNRESOLVED")
        if unknowns:
            return AgentVote(self.agent_id, Domain.TRADING, Layer.INTERPRETATION, "portfolio state indisponible/semantique non resolue", 0.0, Severity.S1, proposed_verdict="HOLD", unknowns=unknowns)
        verdict = "SELL" if state.drawdown > 0.10 or state.exposure > 0.80 else "BUY" if state.exposure < 0.30 and state.drawdown < 0.03 else "HOLD"
        return AgentVote(self.agent_id, Domain.TRADING, Layer.INTERPRETATION, f"exposure={state.exposure:.2f}, drawdown={state.drawdown:.2f}", min(1.0, max(state.drawdown, state.exposure)), Severity.S2 if state.drawdown > 0.10 else Severity.S1, proposed_verdict=verdict)


class ExecutionQualityAgent(BaseAgent):
    agent_id = "ExecutionQualityAgent"
    def evaluate(self, state: TradingState) -> AgentVote:
        # P1-A : spread/slippage inconnus tombaient a 0.0 -> cost_score=0.0
        # -> BUY fabrique (0.0<0.08). Aucune mesure de cout d'execution
        # connue doit produire HOLD + unknown, jamais "execution peu
        # couteuse confirmee".
        spread = state.spreads_bps[-1] if state.spreads_bps else None
        unknowns = []
        if spread is None:
            unknowns.append("MISSING_SPREAD")
        if state.slippage_bps is None:
            unknowns.append("MISSING_SLIPPAGE")
        if unknowns:
            return AgentVote(self.agent_id, Domain.TRADING, Layer.CONTRADICTION, "cout d'execution inconnu", 0.0, Severity.S1, proposed_verdict="HOLD", unknowns=unknowns)
        cost_score = spread / 100 + state.slippage_bps / 100
        verdict = "SELL" if cost_score > 0.25 else "BUY" if cost_score < 0.08 else "HOLD"
        return AgentVote(self.agent_id, Domain.TRADING, Layer.CONTRADICTION, f"execution_cost_score={cost_score:.3f}", min(1.0, cost_score*3), Severity.S2 if verdict=="SELL" else Severity.S1, proposed_verdict=verdict, risk_flags=["POOR_EXECUTION"] if verdict=="SELL" else [])


class RegimeShiftAgent(BaseAgent):
    agent_id = "RegimeShiftAgent"
    def evaluate(self, state: TradingState) -> AgentVote:
        rv20 = realized_volatility(state.prices, 20) or 0.0
        rv5 = realized_volatility(state.prices, 5) or rv20
        verdict = "SELL" if rv5 > rv20 * 1.6 else "HOLD"
        contradictions = ["REGIME_SHIFT_DETECTED"] if verdict == "SELL" else []
        conf = min(1.0, abs((rv5/(rv20 or 0.0001))-1.0))
        return AgentVote(self.agent_id, Domain.TRADING, Layer.CONTRADICTION, f"rv5={rv5:.4f}, rv20={rv20:.4f}", conf, Severity.S3 if verdict=="SELL" else Severity.S1, proposed_verdict=verdict, contradictions=contradictions)


class PortfolioStressAgent(BaseAgent):
    agent_id = "PortfolioStressAgent"
    def evaluate(self, state: TradingState) -> AgentVote:
        # P1-A : exposure/drawdown inconnus a 0.0 produisaient un stress
        # artificiellement bas (jamais SELL). order_book_imbalance seul
        # manquant n'est pas bloquant (poids mineur 0.2, additif) mais reste
        # signale ; exposure/drawdown manquants bloquent le calcul entier --
        # le verdict ne peut jamais deviner un stress "faible" sans eux.
        unknowns = []
        if state.drawdown is None:
            unknowns.append("MISSING_PORTFOLIO_STATE")
        if state.exposure is None:
            unknowns.append("EXPOSURE_SEMANTICS_UNRESOLVED")
        if unknowns:
            return AgentVote(self.agent_id, Domain.TRADING, Layer.CONTRADICTION, "stress portefeuille inconnu", 0.0, Severity.S1, proposed_verdict="HOLD", unknowns=unknowns)
        imbalance_unknown = state.order_book_imbalance is None
        imbalance = state.order_book_imbalance if not imbalance_unknown else 0.0
        stress = min(1.0, state.exposure * 0.8 + state.drawdown * 1.5 + max(0.0, imbalance) * 0.2)
        verdict = "SELL" if stress > 0.7 else "HOLD"
        return AgentVote(self.agent_id, Domain.TRADING, Layer.CONTRADICTION, f"portfolio_stress={stress:.2f}", stress, Severity.S3 if verdict=="SELL" else Severity.S1, proposed_verdict=verdict, risk_flags=["PORTFOLIO_STRESS"] if verdict=="SELL" else [], unknowns=["MISSING_ORDER_BOOK_IMBALANCE"] if imbalance_unknown else [])


class ProofConsistencyAgent(BaseAgent):
    agent_id = "ProofConsistencyAgent"
    def evaluate(self, state: TradingState) -> AgentVote:
        missing = []
        if not state.symbol:
            missing.append("MISSING_SYMBOL")
        if len(state.prices) < 20:
            missing.append("SHORT_PRICE_HISTORY")
        verdict = "HOLD" if missing else "BUY"
        return AgentVote(self.agent_id, Domain.TRADING, Layer.PROOF, "proof consistency for trading payload", 0.9 if not missing else 0.4, Severity.S2 if missing else Severity.S0, proposed_verdict=verdict, unknowns=missing)


def build_trading_agents() -> list[BaseAgent]:
    return [
        MarketDataAgent(),
        LiquidityAgent(),
        VolatilityAgent(),
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
        RegimeShiftAgent(),
        PortfolioStressAgent(),
        ProofConsistencyAgent(),
    ]
