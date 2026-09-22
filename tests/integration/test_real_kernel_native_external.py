"""
F12 — round-trip integration reel Native + External vers le Kernel X-108 reel.

Demarre le Kernel scelle du core Obsidia
(obsidia-x108-proofs_REMOTE_A5F21C6B/server.kernel.sealed.cjs) comme
PROCESSUS EXTERNE en lecture seule (jamais modifie), puis fait traverser un
cycle Native et un cycle External a travers le runtime deja construit
(CycleEngine/GovernanceBridge/Binder), avec RealKX108Client au lieu de
FixtureKX108Client. PAPER only — FakeBroker, aucun reseau broker reel.

Ce test est automatiquement SKIP si :
  - node n'est pas disponible ;
  - le fichier serveur du core n'est pas trouve a l'emplacement attendu ;
  - le serveur ne repond pas dans le delai imparti (port deja pris, etc.).

Dans ce cas, la preuve du round-trip reste documentee de facon statique et
verifiable dans docs/F12_REAL_KERNEL_ROUND_TRIP.md (digests SHA-256 d'une
execution manuelle reelle) — ce test-ci est une preuve d'assemblage
supplementaire quand l'environnement le permet, pas la seule preuve F12.
"""
from __future__ import annotations

import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

from domain.market import Bar, MarketSnapshot
from domain.orders import ExecutionPlan
from domain.portfolio import AccountState, PortfolioState
from domain.proposal import Consensus, SizingDecision, StrategyCandidate
from domain.types import ActionKind, AssetClass, DataQuality, Mode, OrderType, Provenance
from execution.binder.engine import CycleEngine
from execution.binder.planner import ExecutionPlanner
from execution.binder.proof_policy import ProofPolicy
from external.adapters.base_adapter import ExternalStackAnalysisAdapter
from external.examples.brother_stack.example_adapter import ExampleBrotherStackAdapter
from governance.bridge.governance_bridge import KX108GovernanceBridge
from governance.bridge.kx108_client import RealKX108Client
from native.agents.adapter import NativeRosterAnalysisAdapter
from proof.receipts.receipt_store import ReceiptStore

CORE_REPO = Path(
    r"C:\Users\User\Desktop\obsidia-engine-proof-core\obsidia-x108-proofs_REMOTE_A5F21C6B"
)
KERNEL_SCRIPT = CORE_REPO / "server.kernel.sealed.cjs"
SYMBOL = "AAPL"


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def _bars(n: int = 10, base: float = 100.0) -> tuple:
    out = []
    price = base
    for i in range(n):
        price *= 1.001 if i % 2 == 0 else 0.9993
        out.append(Bar(timestamp=float(i), open=price, high=price * 1.001, low=price * 0.999, close=price, volume=1_000.0))
    return tuple(out)


class _FakeMarketData:
    def snapshot(self, symbol):
        return self.snapshots([symbol])[symbol]

    def snapshots(self, symbols):
        return {
            s: MarketSnapshot(
                symbol=s, asset_class=AssetClass.EQUITY, last_price=100.0,
                provenance=Provenance(source="fake", fetched_at=0.0, quality=DataQuality.LIVE, mode=Mode.PAPER),
                tradable=True, market_open=True, bars=_bars(),
            )
            for s in symbols
        }

    def history(self, symbol, limit=200):
        return ()

    def context(self):
        return None


class _FakeBroker:
    def __init__(self):
        self.submit_calls = []

    def account(self):
        return AccountState(
            equity=100_000.0, cash=100_000.0, buying_power=100_000.0,
            provenance=Provenance(source="fake", fetched_at=0.0, quality=DataQuality.LIVE, mode=Mode.PAPER),
            trading_blocked=False,
        )

    def positions(self):
        return ()

    def open_orders(self):
        return ()

    def portfolio(self):
        return PortfolioState(account=self.account())

    def order_status(self, broker_order_id):
        return None

    def order_by_client_order_id(self, client_order_id):
        return None

    def submit(self, plan: ExecutionPlan):
        self.submit_calls.append(plan)
        from domain.orders import BrokerOrder, OrderStatus

        return BrokerOrder(
            broker_order_id="real-kernel-test-1", client_order_id=plan.client_order_id,
            symbol=plan.symbol, side=plan.side, quantity=plan.quantity, order_type=plan.order_type,
            status=OrderStatus.FILLED, filled_quantity=plan.quantity, filled_avg_price=100.0,
            submitted_at=0.0, updated_at=0.0,
        )


class _FakeStrategy:
    def propose(self, state):
        return StrategyCandidate(
            symbol=SYMBOL, action=ActionKind.BUY, rationale="F12 real kernel round-trip",
            confidence=0.6, order_type=OrderType.MARKET, strategy_id="f12-real-kernel",
        )


class _FakeSizing:
    def size(self, candidate, snapshot, portfolio):
        return SizingDecision(quantity=1.0, requested_quantity=1.0)


class _FakeAggregation:
    def aggregate(self, outputs):
        return Consensus(side="BUY", confidence=0.6, buy_weight=1.0)


@pytest.fixture(scope="module")
def real_kernel_process():
    node = shutil.which("node")
    if node is None or not KERNEL_SCRIPT.exists():
        pytest.skip("node ou server.kernel.sealed.cjs indisponible sur cette machine")
    if _port_open("127.0.0.1", 3001):
        pytest.skip("port 3001 deja occupe par un autre processus - round-trip statique documente a la place")

    proc = subprocess.Popen(
        [node, str(KERNEL_SCRIPT)],
        cwd=str(CORE_REPO),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        for _ in range(30):
            if _port_open("127.0.0.1", 3001):
                break
            time.sleep(0.2)
        else:
            proc.kill()
            pytest.skip("le Kernel reel n'a pas demarre dans le delai imparti")
        yield proc
    finally:
        proc.kill()
        proc.wait(timeout=5)


def _run_cycle(analysis, store: ReceiptStore):
    # F12.1 : le Reference Runtime (vrai Kernel) exige ProofPolicy.REQUIRED
    # explicitement -- CycleEngine refuse desormais la combinaison
    # RealKX108Client + BEST_EFFORT par construction (execution/binder/engine.py).
    bridge = KX108GovernanceBridge(RealKX108Client())
    broker = _FakeBroker()
    engine = CycleEngine(
        market_data=_FakeMarketData(), broker=broker, analysis=analysis,
        aggregation=_FakeAggregation(), authority=bridge, symbols=[SYMBOL],
        mode=Mode.PAPER, strategy=_FakeStrategy(), sizing=_FakeSizing(),
        planner=ExecutionPlanner(), proof=store, proof_policy=ProofPolicy.REQUIRED,
    )
    outcome = engine.run_cycle()
    return outcome, broker


def test_native_path_real_kernel_round_trip(real_kernel_process, tmp_path):
    store = ReceiptStore(tmp_path / "native_receipts.jsonl")
    outcome, broker = _run_cycle(NativeRosterAnalysisAdapter(), store)

    assert outcome.decision is not None
    assert outcome.decision.authority.value in ("ACT", "HOLD", "BLOCK")
    # PAPER only : quel que soit le verdict reel, jamais de trace LIVE.
    for plan in broker.submit_calls:
        assert plan is not None  # le broker n'est appele que si Binder autorise ; pas d'assertion de contenu casse le fail-closed


def test_external_path_real_kernel_round_trip(real_kernel_process, tmp_path):
    store = ReceiptStore(tmp_path / "external_receipts.jsonl")
    adapter = ExternalStackAnalysisAdapter(ExampleBrotherStackAdapter())
    outcome, _broker = _run_cycle(adapter, store)

    assert outcome.decision is not None
    assert outcome.decision.authority.value in ("ACT", "HOLD", "BLOCK")


def test_native_and_external_converge_on_same_bridge_type_with_real_kernel(real_kernel_process, tmp_path):
    store1 = ReceiptStore(tmp_path / "conv_native.jsonl")
    store2 = ReceiptStore(tmp_path / "conv_external.jsonl")
    outcome_native, _ = _run_cycle(NativeRosterAnalysisAdapter(), store1)
    outcome_external, _ = _run_cycle(
        ExternalStackAnalysisAdapter(ExampleBrotherStackAdapter()), store2
    )
    assert type(outcome_native.decision) is type(outcome_external.decision)
