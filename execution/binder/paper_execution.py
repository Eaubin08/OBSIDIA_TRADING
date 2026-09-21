"""
Point d'assemblage F6 : Governance Bridge -> Binder -> Alpaca PAPER.

Ce module ne recree PAS le Runtime Binder central d'Obsidia. Il assemble les
pieces deja existantes (execution/binder/engine.py depuis F3, governance/bridge/
depuis F5, market/adapters/alpaca/ depuis F2) pour produire un `CycleEngine`
pret a tourner en mode PAPER uniquement.

Garde-fou non negociable : `require_paper_mode` refuse explicitement toute
configuration Mode.LIVE. Il n'existe aucun chemin de repli silencieux vers le
live — une configuration ambigue ou live leve `LiveModeRejected` avant toute
construction de broker.
"""
from __future__ import annotations

from typing import Optional, Sequence

from domain.ports.clock import ClockPort, SystemClock
from domain.ports.order_ledger import OrderLedgerPort
from domain.types import Mode
from execution.binder.contracts import (
    AggregationPort,
    AnalysisPort,
    AuthorityPort,
    PlannerPort,
)
from execution.binder.engine import CycleEngine
from execution.binder.order_ledger_jsonl import JsonlOrderLedger
from execution.binder.planner import ExecutionPlanner
from governance.bridge.governance_bridge import KX108GovernanceBridge
from governance.bridge.kx108_client import KX108Client
from market.adapters.alpaca.alpaca_broker import AlpacaBroker
from market.adapters.alpaca.alpaca_client import AlpacaHTTPClient
from market.adapters.alpaca.alpaca_config import AlpacaConfig
from market.adapters.alpaca.alpaca_market import AlpacaMarketDataProvider


class LiveModeRejected(RuntimeError):
    """
    Refus structurel d'une configuration Mode.LIVE (ou ambigue) en F6.

    F6 est explicitement PAPER ONLY. Ce n'est pas une limite temporaire du
    code Alpaca lui-meme (market/adapters/alpaca/ reste generique et peut, en
    dehors de ce point d'assemblage, servir a du live si un jour autorise) :
    c'est une decision de ce pipeline precis, qui ne doit jamais basculer en
    live sans une refonte explicite et une revue separee.
    """


def require_paper_mode(config: AlpacaConfig) -> None:
    """Leve LiveModeRejected si la configuration n'est pas explicitement PAPER."""
    if config.mode is not Mode.PAPER:
        raise LiveModeRejected(
            f"OBSIDIA_TRADING/F6 refuse Mode.{config.mode.value} : "
            "seul Mode.PAPER est autorise a ce stade (aucun ordre live)."
        )


def build_paper_cycle_engine(
    *,
    analysis: AnalysisPort,
    aggregation: AggregationPort,
    kx108_client: KX108Client,
    symbols: Sequence[str],
    order_ledger_path: str,
    alpaca_config: Optional[AlpacaConfig] = None,
    planner: Optional[PlannerPort] = None,
    clock: Optional[ClockPort] = None,
) -> CycleEngine:
    """
    Assemble un `CycleEngine` PAPER complet : Bridge -> Binder -> Alpaca.

    `kx108_client` est injecte explicitement — en production, ce doit etre
    une implementation reelle de `KX108Client` (aucune n'existe encore, voir
    docs/B15_STRUCTURAL_SCORE_BOUNDARY.md) ou `UnavailableKX108Client`
    (comportement honnete : fail-closed systematique). Ne JAMAIS passer ici
    un client de test (`FixtureKX108Client`/`StaticKX108TestClient`) : ces
    classes vivent sous tests/test_support/ et ne sont pas importables depuis
    ce module de production (verifie par
    tests/integration/test_paper_execution_pipeline.py::
    test_fixture_client_not_loadable_from_production_config).
    """
    config = alpaca_config or AlpacaConfig.from_env()
    require_paper_mode(config)  # leve LiveModeRejected avant toute construction broker

    clock = clock or SystemClock()
    http_client = AlpacaHTTPClient(config)
    broker = AlpacaBroker(http_client, mode=config.mode, clock=clock)
    market_data = AlpacaMarketDataProvider(http_client, mode=config.mode, clock=clock)
    bridge = KX108GovernanceBridge(kx108_client)
    order_ledger: OrderLedgerPort = JsonlOrderLedger(order_ledger_path)

    return CycleEngine(
        market_data=market_data,
        broker=broker,
        analysis=analysis,
        aggregation=aggregation,
        authority=bridge,
        symbols=list(symbols),
        mode=Mode.PAPER,
        clock=clock,
        planner=planner or ExecutionPlanner(),
        order_ledger=order_ledger,
    )
