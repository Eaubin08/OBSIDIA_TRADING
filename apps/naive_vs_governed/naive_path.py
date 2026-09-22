"""
apps/naive_vs_governed/naive_path.py

NAIVE = COUNTERFACTUAL DEMO uniquement.

Calcule "qu'aurait-on fait sans gouvernance" a partir des memes signaux bruts
d'agent (AgentVote) que le chemin Governed observe. Isolation stricte et
DELIBEREE : ce fichier n'importe et ne peut jamais importer
``governance.bridge`` (KX108Client / GovernanceBridge), ``execution.binder``
(Binder / CycleEngine), ``market.adapters.alpaca`` (broker), ni
``domain.contracts.canonical`` (``to_canonical_agent_signal``) — voir
tests/unit/test_naive_vs_governed.py pour la preuve structurelle.

Pourquoi ce fichier duplique une petite fonction (bars -> TradingState) deja
presente dans native/agents/adapter.py plutot que de l'importer : ce module
adapter.py importe lui-meme ``domain.contracts.canonical`` (pour le chemin
Governed reel). Importer quoi que ce soit depuis ``native.agents.adapter``
introduirait une dependance transitive vers le canonical builder dans le
code Naive, meme si la fonction canonique n'est jamais appelee — ce qui
romprait l'isolation structurelle exigee par la demonstration. La
duplication ci-dessous est volontaire et minimale (une seule fonction pure,
sans effet de bord) ; les deux transformations restent identiques par
construction (memes champs de ``Bar`` lus dans le meme ordre), ce que
``tests/unit/test_naive_vs_governed.py`` verifie explicitement (« memes
entrees dans les deux chemins »).

Le Naive suit uniquement le signal dominant (le vote le plus frequent parmi
les 17 agents), en ignorant deliberement unknowns/contradictions/risk_flags
— c'est precisement ce que la demonstration montre : la difference entre
agir sur un signal brut et agir sous une gouvernance qui preserve ces
informations jusqu'a la decision.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Sequence, Tuple, Type

from domain.market import MarketSnapshot

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

# Meme roster de 17 agents que native/agents/adapter.py::ROSTER_17, mais
# importe directement depuis native.agents.domains.trading_agents — jamais
# via native.agents.adapter, pour ne pas introduire de dependance transitive
# vers domain.contracts.canonical dans le code Naive.
NAIVE_ROSTER: Tuple[Type, ...] = (
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


def trading_state_from_snapshot_naive(symbol: str, snapshot: MarketSnapshot) -> TradingState:
    """
    Duplication volontaire et minimale de
    native/agents/adapter.py::trading_state_from_snapshot — voir docstring
    de module. Memes champs lus dans le meme ordre : le resultat est
    identique par construction pour les memes bars.
    """
    bars = snapshot.bars
    prices = [b.close for b in bars] if bars else [snapshot.last_price]
    highs = [b.high for b in bars] if bars else [snapshot.last_price]
    lows = [b.low for b in bars] if bars else [snapshot.last_price]
    volumes = [b.volume for b in bars] if bars else [snapshot.volume or 0.0]
    return TradingState(symbol=symbol, prices=prices, highs=highs, lows=lows, volumes=volumes)


def raw_votes(symbol: str, snapshot: MarketSnapshot) -> Tuple[AgentVote, ...]:
    """Appelle chaque agent DIRECTEMENT (``agent.evaluate(state)``) — jamais
    via un AnalysisPort, jamais via ``agent_vote_to_agent_output``."""
    state = trading_state_from_snapshot_naive(symbol, snapshot)
    return tuple(cls().evaluate(state) for cls in NAIVE_ROSTER)


@dataclass(frozen=True)
class NaiveOutcome:
    """
    COUNTERFACTUAL DEMO uniquement. Ne represente JAMAIS un ordre reellement
    executable : ce dataclass n'a aucun chemin vers un broker, un Binder, ou
    une CanonicalDecision. Il documente « ce qu'un systeme sans gouvernance
    aurait fait », pour la seule fin de comparaison pedagogique.
    """

    label: str
    dominant_signal: str
    vote_counts: Tuple[Tuple[str, int], ...]
    candidate_action: str
    predicted_exposure: float
    predicted_risk_note: str
    simulated_result_note: str
    ignored_unknowns: Tuple[str, ...]
    ignored_contradictions: Tuple[str, ...]
    ignored_risk_flags: Tuple[str, ...]
    source_votes: Tuple[AgentVote, ...]


NAIVE_LABEL = "NAIVE = COUNTERFACTUAL DEMO"


def naive_counterfactual(
    votes: Sequence[AgentVote], *, last_price: float, quantity: float = 1.0
) -> NaiveOutcome:
    """Calcule le contrefactuel Naive a partir d'AgentVote deja produits.
    N'invente aucune donnee supplementaire."""
    votes = list(votes)
    counts = Counter(v.proposed_verdict for v in votes)
    dominant = counts.most_common(1)[0][0] if counts else "HOLD"

    ignored_unknowns = tuple(u for v in votes for u in (v.unknowns or ()))
    ignored_contradictions = tuple(c for v in votes for c in (v.contradictions or ()))
    ignored_risk_flags = tuple(r for v in votes for r in (v.risk_flags or ()))

    if dominant in ("BUY", "SELL"):
        candidate_action = f"{dominant} {quantity:g} @ ~{last_price:.2f}"
        predicted_exposure = quantity * last_price
    else:
        candidate_action = "HOLD (signal dominant = HOLD)"
        predicted_exposure = 0.0

    return NaiveOutcome(
        label=NAIVE_LABEL,
        dominant_signal=dominant,
        vote_counts=tuple(sorted(counts.items())),
        candidate_action=candidate_action,
        predicted_exposure=predicted_exposure,
        predicted_risk_note=(
            "Naive ne consulte aucun risk_flag/unknown/contradiction pour cette "
            "decision — seul le signal dominant compte."
        ),
        simulated_result_note=(
            "Contrefactuel non-execute : aucun ordre n'a ete ni ne sera soumis par ce "
            "chemin (aucun acces broker). 'Simule' signifie ici 'ce qu'aurait propose "
            "un systeme sans gouvernance', pas un backtest financier valide — le "
            "dataset est le snapshot synthetique deterministe de "
            "apps/cockpit/demo_doubles.py, aucun resultat n'est generalisable."
        ),
        ignored_unknowns=ignored_unknowns,
        ignored_contradictions=ignored_contradictions,
        ignored_risk_flags=ignored_risk_flags,
        source_votes=tuple(votes),
    )


def run_naive_path(symbol: str, snapshot: MarketSnapshot, *, quantity: float = 1.0) -> NaiveOutcome:
    """Point d'entree unique du chemin Naive : observation -> votes bruts ->
    contrefactuel. Aucune etape ici ne touche governance/execution/proof."""
    votes = raw_votes(symbol, snapshot)
    return naive_counterfactual(votes, last_price=snapshot.last_price, quantity=quantity)
