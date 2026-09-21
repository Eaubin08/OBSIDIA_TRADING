"""
apps/cockpit/scenarios.py — F9.

Catalogue des scenarios de demo. Chaque scenario construit et execute un VRAI
``CycleEngine`` (execution/binder/engine.py, F3/F6) avec les memes briques deja
prouvees en F8.5/F8.6 : ``KX108GovernanceBridge`` (F5) branche sur
``FixtureKX108Client`` (TEST-ONLY, tests/test_support/), ``NativeRosterAnalysisAdapter``
(roster de 17 agents, F3/F8.7) ou ``ExternalStackAnalysisAdapter`` +
``ExampleBrotherStackAdapter`` (F8), ``ExecutionPlanner`` (F6), et persiste
dans un ``ReceiptStore`` (F7) partage entre scenarios.

CE MODULE NE DECIDE RIEN. Il assemble des composants deja prouves separement
et retourne ce qu'ils ont produit. UI != Authority : aucune ligne ici ne
calcule un verdict ACT/HOLD/BLOCK ni une permission Binder — ces valeurs
viennent exclusivement de KX108GovernanceBridge et de ExecutionPlanner.
"""
from __future__ import annotations

import warnings
from dataclasses import asdict, dataclass

from apps.cockpit.demo_doubles import (
    SYMBOL,
    DemoAggregation,
    DemoBroker,
    DemoMarketData,
    DemoSizing,
    DemoStrategy,
    failing_submit,
)
from domain.types import Mode
from execution.binder.engine import CycleEngine, CycleOutcome
from execution.binder.order_ledger_jsonl import JsonlOrderLedger
from execution.binder.planner import ExecutionPlanner
from external.adapters.base_adapter import ExternalStackAnalysisAdapter
from external.examples.brother_stack.example_adapter import ExampleBrotherStackAdapter
from governance.bridge.governance_bridge import KX108GovernanceBridge
from native.agents.adapter import NativeRosterAnalysisAdapter
from proof.receipts.receipt_chain import (
    SIMULATION_EXTENSION_KEY,
    SIMULATION_KIND_TRADING_WORLD,
    build_simulation_extension,
)
from proof.receipts.receipt_store import ReceiptStore
from simulation.trading_world.market_process import TradingParams, run_trading_simulation
from tests.test_support.kx108_fixtures import FixtureKX108Client

TRADING_PARAMS = TradingParams(
    seed=42, steps=20, s0=100.0, mu=0.05, sigma=0.2, dt=1 / 252,
    jump_lambda=0.01, jump_mu=-0.02, jump_sigma=0.03,
    garch_alpha=0.1, garch_beta=0.85, garch_omega=0.0001,
    regimes=2, friction_bps=5.0,
)


def _fixture_client(verdict: str) -> FixtureKX108Client:
    """
    FixtureKX108Client leve un RuntimeWarning a la construction — TEST-ONLY,
    jamais un fallback runtime (voir tests/test_support/kx108_fixtures.py).
    Le Cockpit connait deja et affiche cet avertissement explicitement
    (section KX108 de la vue), donc on l'attrape ici plutot que de le laisser
    remonter dans les logs applicatifs sans contexte.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return FixtureKX108Client(verdict=verdict)


class _DeferredSimulationProof:
    """
    Proxy du Protocol ``domain.ports.proof.ProofPort`` (``last_hash``/``record``).

    ``previous_hash`` continue de chainer sur le vrai ``store`` partage du
    Cockpit, mais la persistance elle-meme est DIFFEREE : ``record()`` est un
    no-op. Ceci permet d'attacher la simulation F4 comme Evidence
    (``receipt.extensions``) AVANT la persistance reelle — meme contrainte que
    F8.5 scenario 1 — sans casser la continuite de la chaine partagee entre
    scenarios du Cockpit. L'appelant (``run_scenario`` ci-dessous) persiste
    manuellement via ``store.record(receipt)`` une fois l'extension attachee.

    Ceci ne cree AUCUN nouveau mecanisme de preuve : c'est un simple relais
    vers ``ReceiptStore.last_hash()``, jamais un second ecrivain concurrent.
    """

    def __init__(self, store: ReceiptStore) -> None:
        self._store = store

    def last_hash(self) -> str:
        return self._store.last_hash()

    def record(self, receipt):
        return receipt


@dataclass(frozen=True)
class ScenarioSpec:
    key: str
    label: str
    description: str
    mode: str  # "native" | "external"
    verdict: str  # ACT | HOLD | BLOCK
    trading_blocked: bool = False
    submit_fails: bool = False
    attach_simulation: bool = False


SCENARIOS = (
    ScenarioSpec(
        "native_act_paper_success", "1. Native + ACT + Binder allow + PAPER success",
        "Roster natif (17 agents), KX108=ACT, Binder autorise, simulation F4 attachee comme Evidence, un ordre PAPER soumis.",
        mode="native", verdict="ACT", attach_simulation=True,
    ),
    ScenarioSpec(
        "native_hold", "2. Native + HOLD",
        "KX108=HOLD : aucun ordre, aucun effet de bord broker, receipt quand meme produit.",
        mode="native", verdict="HOLD",
    ),
    ScenarioSpec(
        "native_block", "3. Native + BLOCK",
        "KX108=BLOCK : aucune execution, raison tracable dans le receipt, provenance conservee.",
        mode="native", verdict="BLOCK",
    ),
    ScenarioSpec(
        "act_binder_refuses", "4. ACT + Binder refuse",
        "KX108=ACT mais compte bloque cote broker : le Binder refuse quand meme. Decision != Permission.",
        mode="native", verdict="ACT", trading_blocked=True,
    ),
    ScenarioSpec(
        "broker_failure", "5. Broker failure",
        "KX108=ACT, Binder autorise, mais le broker PAPER (fake) echoue a la soumission : echec explicite, jamais un faux succes.",
        mode="native", verdict="ACT", submit_fails=True,
    ),
    ScenarioSpec(
        "external_act", "6. External + ACT",
        "Stack externe fictive (brother_strategy_07, F8) via l'External Adapter : meme Bridge, meme Binder, meme execution que le natif.",
        mode="external", verdict="ACT", attach_simulation=True,
    ),
    ScenarioSpec(
        "external_block", "7. External + BLOCK",
        "Meme chemin externe, KX108=BLOCK : aucune execution, provenance externe (source_id/adapter_id/organization_id) conservee.",
        mode="external", verdict="BLOCK",
    ),
)
# Le 8e scenario ("Replay") n'est pas un cycle a executer : c'est une action de
# consultation sur un cycle DEJA persiste par un des scenarios ci-dessus.
# Voir replay_previous_cycle() en bas de ce module.


def scenario_by_key(key: str) -> ScenarioSpec:
    for spec in SCENARIOS:
        if spec.key == key:
            return spec
    raise KeyError(f"scenario inconnu: {key}")


def _analysis_for(mode: str):
    if mode == "external":
        return ExternalStackAnalysisAdapter(ExampleBrotherStackAdapter())
    return NativeRosterAnalysisAdapter()


def run_scenario(spec: ScenarioSpec, store: ReceiptStore) -> CycleOutcome:
    """
    Execute REELLEMENT un cycle pour ce scenario via le vrai CycleEngine et
    persiste le receipt dans ``store``. Le verdict vient exclusivement de
    ``FixtureKX108Client`` (TEST-ONLY) via le vrai ``KX108GovernanceBridge``,
    la permission vient exclusivement du vrai Binder
    (``execution/binder/planner.py``). Ce module ne fabrique ni l'un ni l'autre.
    """
    broker = DemoBroker(
        trading_blocked=spec.trading_blocked,
        submit_behavior=failing_submit if spec.submit_fails else None,
    )
    ledger = JsonlOrderLedger(store.path.with_name(store.path.stem + "-ledger.jsonl"))
    bridge = KX108GovernanceBridge(_fixture_client(spec.verdict))

    proof = _DeferredSimulationProof(store) if spec.attach_simulation else store

    engine = CycleEngine(
        market_data=DemoMarketData(),
        broker=broker,
        analysis=_analysis_for(spec.mode),
        aggregation=DemoAggregation(),
        authority=bridge,
        symbols=[SYMBOL],
        mode=Mode.PAPER,
        strategy=DemoStrategy(),
        sizing=DemoSizing(),
        planner=ExecutionPlanner(),
        order_ledger=ledger,
        proof=proof,
    )
    outcome = engine.run_cycle()

    if spec.attach_simulation and outcome.receipt is not None:
        steps, returns = run_trading_simulation(TRADING_PARAMS)
        extension = build_simulation_extension(
            kind=SIMULATION_KIND_TRADING_WORLD, seed=TRADING_PARAMS.seed,
            params=asdict(TRADING_PARAMS), engine_version="market_process.v1",
            steps=steps, returns=returns,
        )
        # Mutation du dict `extensions` (mutable dans un frozen dataclass) —
        # mecanisme documente par F7/F8.5, jamais une reassignation du receipt.
        outcome.receipt.extensions[SIMULATION_EXTENSION_KEY] = extension
        store.record(outcome.receipt)

    return outcome


def replay_previous_cycle(store: ReceiptStore, cycle_id: str):
    """
    Scenario 8 — Replay. Reutilise ``ReplayEngine`` (F7) tel quel : aucune
    nouvelle logique de rejeu ici. Retourne (audit_result, deterministic_result).
    Garantie deja prouvee en F7/F8.5/F8.6 : zero appel broker pendant un replay.
    """
    from proof.receipts.replay import ReplayEngine

    replay = ReplayEngine(store)
    audit = replay.replay_audit(cycle_id)
    deterministic = replay.replay_deterministic(cycle_id)
    return audit, deterministic
