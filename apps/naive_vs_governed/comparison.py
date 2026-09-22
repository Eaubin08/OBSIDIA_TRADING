"""
apps/naive_vs_governed/comparison.py

Assemble la comparaison NAIVE vs GOVERNED pour un scenario donne. Ce module
NE RECALCULE JAMAIS la gouvernance et NE FABRIQUE JAMAIS de verdict.

Cote GOVERNED : reutilise integralement apps/cockpit/scenarios.py::run_scenario
(F9 — lui-meme un assemblage de CycleEngine/KX108GovernanceBridge/
ExecutionPlanner deja proves F3-F8.7) et apps/cockpit/presenter.py::
build_cockpit_view pour la representation descriptive. Rien n'est duplique.

Cote NAIVE : delegue integralement a apps/naive_vs_governed/naive_path.py,
strictement isole de governance.bridge / execution.binder /
market.adapters.alpaca / domain.contracts.canonical.

MEME ENTREE pour les deux chemins : le meme ``DemoMarketData`` (memes bars
synthetiques deterministes, meme prix de reference) alimente a la fois le
calcul Naive (agents appeles directement, naive_path.py) et le cycle
Governed (via NativeRosterAnalysisAdapter ou ExternalStackAnalysisAdapter,
memes bars, memes agents pour le chemin natif). Voir
tests/unit/test_naive_vs_governed.py pour la preuve d'egalite des entrees.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from apps.cockpit.demo_doubles import SYMBOL, DemoMarketData
from apps.cockpit.presenter import KX108_FIXTURE_BANNER, build_cockpit_view
from apps.cockpit.scenarios import run_scenario, scenario_by_key
from apps.naive_vs_governed.naive_path import NAIVE_LABEL, NaiveOutcome, run_naive_path
from execution.binder.engine import CycleOutcome
from execution.binder.paper_execution import LiveModeRejected, require_paper_mode
from domain.types import Mode
from market.adapters.alpaca.alpaca_config import AlpacaConfig
from proof.receipts.receipt_store import ReceiptStore

PAPER_ONLY_LABEL = "PAPER ONLY"


@dataclass(frozen=True)
class NaiveVsGovernedScenario:
    key: str
    letter: str
    title: str
    narrative: str
    # None pour le scenario E : aucun CycleEngine n'est construit (le refus
    # se produit avant meme la connexion Alpaca, voir _live_rejection_demo).
    governed_scenario_key: Optional[str]


SCENARIOS = (
    NaiveVsGovernedScenario(
        "A_banal", "A", "Banal / admissible",
        "Le signal est propre : Naive agirait, Governed aussi (KX108=ACT, Binder=ALLOW). "
        "Demontre que la gouvernance ne bloque pas arbitrairement tout.",
        governed_scenario_key="native_act_paper_success",
    ),
    NaiveVsGovernedScenario(
        "B_unknown", "B", "Unknown critique",
        "Naive suit le signal brut. Governed conserve les unknowns surfaces par "
        "ProofConsistencyAgent (champs de marche absents du snapshot demo — gap "
        "documente dans native/agents/adapter.py). Le fixture KX108 est place a HOLD "
        "pour representer ce qu'un vrai Kernel ferait face a cette incertitude non "
        "resolue — le fixture ne LIT PAS reellement les unknowns (TEST-ONLY, voir "
        "docs/B15_STRUCTURAL_SCORE_BOUNDARY.md), c'est un choix narratif explicite.",
        governed_scenario_key="native_hold",
    ),
    NaiveVsGovernedScenario(
        "C_contradiction", "C", "Contradiction agents",
        "Naive ne retient que le signal dominant. Governed conserve les "
        "contradictions/risk_flags de tous les agents (RegimeShiftAgent, "
        "VolatilityAgent, PortfolioStressAgent). Fixture KX108 place a BLOCK pour la "
        "meme raison narrative que le scenario B.",
        governed_scenario_key="native_block",
    ),
    NaiveVsGovernedScenario(
        "D_authority_vs_permission", "D", "Autorite vs permission",
        "KX108=ACT mais le Binder refuse (compte bloque cote broker) : "
        "DECISION != PERMISSION.",
        governed_scenario_key="act_binder_refuses",
    ),
    NaiveVsGovernedScenario(
        "E_live_forbidden", "E", "Environnement interdit (LIVE)",
        "Tentative de configuration Mode.LIVE : refusee structurellement avant toute "
        "connexion (execution/binder/paper_execution.py::require_paper_mode, F6, "
        "reutilise tel quel, non modifie). Naive n'a de toute facon aucun acces "
        "broker, live ou paper.",
        governed_scenario_key=None,
    ),
    NaiveVsGovernedScenario(
        "F_broker_failure", "F", "Broker failure",
        "KX108=ACT, Binder=ALLOW, mais le broker PAPER (fake) echoue a la "
        "soumission : Governed produit une FAILURE RECEIPT explicite, jamais un "
        "faux succes.",
        governed_scenario_key="broker_failure",
    ),
    NaiveVsGovernedScenario(
        "G_external", "G", "External stack",
        "Meme scenario, mais la cognition vient d'une stack externe fictive "
        "(brother_strategy_07, F8) au lieu du roster natif. Meme Bridge, meme "
        "Binder, meme execution : la demonstration n'est pas limitee aux agents "
        "Native.",
        governed_scenario_key="external_act",
    ),
)


def scenario_by_letter(letter: str) -> NaiveVsGovernedScenario:
    for spec in SCENARIOS:
        if spec.letter == letter:
            return spec
    raise KeyError(f"scenario Naive vs Governed inconnu: {letter}")


def shared_market_snapshot(*, last_price: float = 100.0):
    """Meme instance de donnees de marche pour les deux chemins de ce scenario."""
    return DemoMarketData(last_price=last_price).snapshot(SYMBOL)


def _live_rejection_demo() -> Dict[str, Any]:
    """
    Scenario E : aucun CycleEngine n'est construit — F6 refuse Mode.LIVE
    avant meme la construction d'un client Alpaca. Reutilise
    require_paper_mode() tel quel (execution/binder/paper_execution.py,
    non modifie) pour prouver le refus structurel.
    """
    live_config = AlpacaConfig(mode=Mode.LIVE, api_key="", secret_key="", trading_base_url="")
    try:
        require_paper_mode(live_config)
        refused, detail = False, "ERREUR DE DEMO : LiveModeRejected non leve."
    except LiveModeRejected as exc:
        refused, detail = True, str(exc)
    return {
        "attempted_mode": Mode.LIVE.value,
        "refused": refused,
        "detail": detail,
        "mechanism": "execution.binder.paper_execution.require_paper_mode (F6, non modifie)",
        "naive_live_capability": "NONE — le code Naive n'importe aucun module broker.",
    }


@dataclass(frozen=True)
class ComparisonResult:
    scenario: NaiveVsGovernedScenario
    naive: NaiveOutcome
    governed_outcome: Optional[CycleOutcome]
    governed_view: Optional[Dict[str, Any]]
    live_rejection: Optional[Dict[str, Any]]
    labels: Dict[str, str]


def build_comparison(letter: str, store: ReceiptStore) -> ComparisonResult:
    """
    Point d'entree unique de la demo. NE DECIDE RIEN : delegue integralement
    au chemin Naive isole (naive_path.py) et au chemin Governed deja prouve
    (apps.cockpit.scenarios.run_scenario + apps.cockpit.presenter.build_cockpit_view).
    """
    spec = scenario_by_letter(letter)
    snapshot = shared_market_snapshot()
    naive = run_naive_path(SYMBOL, snapshot)

    governed_outcome: Optional[CycleOutcome] = None
    governed_view: Optional[Dict[str, Any]] = None
    live_rejection: Optional[Dict[str, Any]] = None

    if spec.governed_scenario_key is not None:
        governed_spec = scenario_by_key(spec.governed_scenario_key)
        governed_outcome = run_scenario(governed_spec, store)
        governed_view = build_cockpit_view(governed_outcome, store)
    else:
        live_rejection = _live_rejection_demo()

    return ComparisonResult(
        scenario=spec,
        naive=naive,
        governed_outcome=governed_outcome,
        governed_view=governed_view,
        live_rejection=live_rejection,
        labels={
            "naive": NAIVE_LABEL,
            "kx108_fixture": KX108_FIXTURE_BANNER if governed_outcome is not None else "N/A — scenario E n'invoque aucun KX108",
            "paper_only": PAPER_ONLY_LABEL,
        },
    )
