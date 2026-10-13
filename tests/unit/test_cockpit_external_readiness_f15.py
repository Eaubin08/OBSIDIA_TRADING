"""
F15 — le Cockpit rend visible "ce que la stack externe propose" separement
de la gouvernance. Lecture seule des objets deja produits par le runtime :
aucune fonction testee ici ne doit fabriquer une Authority/Decision.
"""
from __future__ import annotations

import warnings

from apps.cockpit.presenter import build_cockpit_view
from domain.market import MarketSnapshot
from domain.orders import ExecutionResult
from domain.portfolio import AccountState, PortfolioState
from domain.proposal import Consensus, SizingDecision, StrategyCandidate
from domain.types import ActionKind, AssetClass, DataQuality, Mode, OrderStatus, OrderType, Provenance
from execution.binder.engine import CycleEngine
from execution.binder.planner import ExecutionPlanner
from external.adapters.base_adapter import ExternalStackAnalysisAdapter
from external.examples.brother_stack.example_adapter import ExampleBrotherStackAdapter
from governance.bridge.governance_bridge import KX108GovernanceBridge
from native.agents.adapter import NativeRosterAnalysisAdapter
from proof.receipts.receipt_store import ReceiptStore
from tests.test_support.kx108_fixtures import FixtureKX108Client


class _FakeMarketData:
    def snapshot(self, symbol):
        return self.snapshots([symbol])[symbol]

    def snapshots(self, symbols):
        return {
            s: MarketSnapshot(
                symbol=s, asset_class=AssetClass.EQUITY, last_price=100.0,
                provenance=Provenance(source="fake", fetched_at=0.0,
                                       quality=DataQuality.LIVE, mode=Mode.PAPER),
                tradable=True, market_open=True,
            )
            for s in symbols
        }

    def history(self, symbol, limit=200):
        return ()

    def context(self):
        return None


class _FakeBroker:
    def account(self):
        return AccountState(equity=100_000.0, cash=100_000.0, buying_power=100_000.0,
                             provenance=Provenance(source="fake", fetched_at=0.0,
                                                    quality=DataQuality.LIVE, mode=Mode.PAPER),
                             trading_blocked=False)

    def positions(self):
        return ()

    def open_orders(self):
        return ()

    def portfolio(self):
        return PortfolioState(account=self.account())

    def submit(self, plan):
        return ExecutionResult(plan=plan, submitted=True, status=OrderStatus.ACCEPTED,
                                broker_order_id="fake-1", mode=Mode.PAPER.value)

    def close_position(self, plan):
        raise NotImplementedError


class _FakeAggregation:
    def aggregate(self, outputs):
        return Consensus(side="BUY", confidence=0.9)


class _FakeStrategy:
    def build(self, symbol, snapshot, consensus, portfolio, opportunities=()):
        return (StrategyCandidate(symbol=symbol, action=ActionKind.BUY, rationale="f15 cockpit test",
                                   confidence=0.9, order_type=OrderType.MARKET,
                                   strategy_id="fixture-strategy"),)


class _FakeSizing:
    def size(self, candidate, snapshot, portfolio):
        return SizingDecision(quantity=1.0, requested_quantity=1.0)


def _run_cycle(analysis, tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        kx108 = FixtureKX108Client(verdict="ACT")
    bridge = KX108GovernanceBridge(kx108)
    store = ReceiptStore(tmp_path / "receipts.jsonl")
    engine = CycleEngine(
        market_data=_FakeMarketData(), broker=_FakeBroker(), analysis=analysis,
        aggregation=_FakeAggregation(), authority=bridge, symbols=["AAPL"], mode=Mode.PAPER,
        strategy=_FakeStrategy(), sizing=_FakeSizing(), planner=ExecutionPlanner(), proof=store,
    )
    return engine.run_cycle(), store


def test_cockpit_shows_external_stack_detail_when_source_is_external(tmp_path):
    outcome, store = _run_cycle(
        ExternalStackAnalysisAdapter(ExampleBrotherStackAdapter()), tmp_path
    )
    view = build_cockpit_view(outcome, store)
    readiness = view["input"]["external_stack_readiness"]

    assert readiness["present"] is True
    signal = readiness["signals"][0]
    assert signal["stack_id"] == "brother_strategy_07"
    assert signal["adapter_id"] == "brother_stack_v1"
    assert signal["organization_id"] == "brother_company"
    assert signal["proposal"] == "BUY"
    # Fixture pedagogique : pas de calibration externe fournie -> sentinelle
    # explicite, jamais une valeur inventee.
    assert signal["external_calibration_id"] == "NO_EXTERNAL_CALIBRATION_INFORMATION"


def test_cockpit_external_stack_detail_empty_for_native_cycle(tmp_path):
    outcome, store = _run_cycle(NativeRosterAnalysisAdapter(), tmp_path)
    view = build_cockpit_view(outcome, store)
    readiness = view["input"]["external_stack_readiness"]

    assert readiness["present"] is False
    assert readiness["signals"] == []
    # La frontiere reste visible : Native n'est pas affecte par F15.
    assert view["input"]["source_systems_observed"] == ["native"]
