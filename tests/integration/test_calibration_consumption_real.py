"""
F13.1 — round-trip reel: donnees Alpaca reelles -> CalibrationPack ->
agents Native calibres -> convergence canonique -> vrai Kernel X-108 ->
Binder -> PAPER -> PROOF_REQUIRED.

Reutilise le pattern .env de tests/integration/test_real_market_calibration.py
(chargement via monkeypatch, jamais affiche/logge/commite, skip propre si
credentials absents). Reutilise le pattern Kernel reel de
tests/integration/test_real_kernel_native_external.py (F12).

Anti-tuning : aucun parametre de calibration n'est jamais ajuste en
fonction du verdict Kernel observe ici ou ailleurs.
"""
from __future__ import annotations

import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

from domain.calibration_consumption import build_full_real_calibration_pack
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
from market.adapters.alpaca.real_dataset_attempt import attempt_real_historical_dataset_with_closes
from native.agents.adapter import NativeRosterAnalysisAdapter
from native.agents.calibrated_agents import build_calibrated_trading_agents
from native.agents.contracts import TradingState
from proof.receipts.receipt_store import ReceiptStore

ENV_PATH = Path(".env")
CORE_REPO = Path(r"C:\Users\User\Desktop\obsidia-engine-proof-core\obsidia-x108-proofs_REMOTE_A5F21C6B")
KERNEL_SCRIPT = CORE_REPO / "server.kernel.sealed.cjs"
SYMBOL = "AAPL"


def _load_env_pairs() -> dict:
    if not ENV_PATH.exists():
        return {}
    text = ENV_PATH.read_bytes().decode("utf-8-sig")
    return {k.strip(): v.strip() for line in text.splitlines() if "=" in line and line.strip() for k, v in [line.split("=", 1)]}


@pytest.fixture()
def real_alpaca_env(monkeypatch):
    pairs = _load_env_pairs()
    api_key = pairs.get("ALPACA_API_KEY", "").strip()
    secret_key = pairs.get("ALPACA_SECRET_KEY", "").strip()
    if not api_key or not secret_key:
        pytest.skip(".env absent ou credentials Alpaca vides sur cette machine")
    for k, v in pairs.items():
        monkeypatch.setenv(k, v)
    yield


@pytest.fixture(scope="module")
def real_kernel_process():
    node = shutil.which("node")
    if node is None or not KERNEL_SCRIPT.exists():
        pytest.skip("node ou server.kernel.sealed.cjs indisponible")

    def _port_open(host, port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.3)
            return sock.connect_ex((host, port)) == 0

    if _port_open("127.0.0.1", 3001):
        pytest.skip("port 3001 deja occupe")

    proc = subprocess.Popen([node, str(KERNEL_SCRIPT)], cwd=str(CORE_REPO),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        for _ in range(30):
            if _port_open("127.0.0.1", 3001):
                break
            time.sleep(0.2)
        else:
            proc.kill()
            pytest.skip("Kernel n'a pas demarre a temps")
        yield proc
    finally:
        proc.kill()
        proc.wait(timeout=5)


def _real_pack():
    ds, closes = attempt_real_historical_dataset_with_closes(
        symbol=SYMBOL, timeframe="1Day", limit=250, lookback_days=250
    )
    if not ds.is_real:
        pytest.skip(f"Alpaca n'a pas retourne de donnees reelles: {ds.quality_flags}")
    from domain.calibration_estimation import log_returns_from_closes
    returns = log_returns_from_closes(closes)
    return build_full_real_calibration_pack(ds, returns), closes


def _bars_from_closes(closes) -> tuple:
    out = []
    for i, c in enumerate(closes):
        out.append(Bar(timestamp=float(i), open=c, high=c * 1.001, low=c * 0.999, close=c, volume=1_000.0))
    return tuple(out)


class _FakeMarketData:
    def __init__(self, closes):
        self._closes = closes

    def snapshot(self, symbol):
        return self.snapshots([symbol])[symbol]

    def snapshots(self, symbols):
        return {
            s: MarketSnapshot(
                symbol=s, asset_class=AssetClass.EQUITY, last_price=self._closes[-1],
                provenance=Provenance(source="alpaca_real", fetched_at=0.0, quality=DataQuality.LIVE, mode=Mode.PAPER),
                tradable=True, market_open=True, bars=_bars_from_closes(self._closes),
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
            broker_order_id="f13-1-real-calib-1", client_order_id=plan.client_order_id,
            symbol=plan.symbol, side=plan.side, quantity=plan.quantity, order_type=plan.order_type,
            status=OrderStatus.FILLED, filled_quantity=plan.quantity, filled_avg_price=100.0,
            submitted_at=0.0, updated_at=0.0,
        )


class _FakeStrategy:
    def propose(self, state):
        return StrategyCandidate(
            symbol=SYMBOL, action=ActionKind.BUY, rationale="F13.1 calibrated real round-trip",
            confidence=0.6, order_type=OrderType.MARKET, strategy_id="f13-1-calibrated",
        )


class _FakeSizing:
    def size(self, candidate, snapshot, portfolio):
        return SizingDecision(quantity=1.0, requested_quantity=1.0)


class _FakeAggregation:
    def aggregate(self, outputs):
        return Consensus(side="BUY", confidence=0.6, buy_weight=1.0)


def _run_calibrated_native_cycle(pack, closes, store: ReceiptStore):
    roster = build_calibrated_trading_agents(pack)
    analysis = NativeRosterAnalysisAdapter(agent_classes=roster)
    bridge = KX108GovernanceBridge(RealKX108Client())
    broker = _FakeBroker()
    engine = CycleEngine(
        market_data=_FakeMarketData(closes), broker=broker, analysis=analysis,
        aggregation=_FakeAggregation(), authority=bridge, symbols=[SYMBOL],
        mode=Mode.PAPER, strategy=_FakeStrategy(), sizing=_FakeSizing(),
        planner=ExecutionPlanner(), proof=store, proof_policy=ProofPolicy.REQUIRED,
    )
    return engine.run_cycle(), broker


# 10. Native path utilise reellement le CalibrationPack (via le roster calibre)
def test_native_calibrated_roster_real_kernel_round_trip(real_alpaca_env, real_kernel_process, tmp_path):
    pack, closes = _real_pack()
    store = ReceiptStore(tmp_path / "native_calibrated_receipts.jsonl")
    outcome, broker = _run_calibrated_native_cycle(pack, closes, store)
    assert outcome.decision is not None
    assert outcome.decision.authority.value in ("ACT", "HOLD", "BLOCK")
    # PROOF_REQUIRED actif : aucune exception levee => la preuve pre-execution
    # a ete joignable, quel que soit le verdict.


# 13. Real Kernel fonctionne encore avec le roster calibre
def test_real_kernel_still_functions_with_calibrated_agents(real_alpaca_env, real_kernel_process, tmp_path):
    pack, closes = _real_pack()
    store = ReceiptStore(tmp_path / "kernel_still_functions.jsonl")
    outcome, _ = _run_calibrated_native_cycle(pack, closes, store)
    assert outcome.decision.authority.value in ("ACT", "HOLD", "BLOCK")


# 14/15/16. PROOF_REQUIRED, PAPER_ONLY, Binder jamais contourne (verifie par
# construction : CycleEngine leve RealKernelRequiresProofRequired si on tente
# BEST_EFFORT + RealKX108Client -- teste ici explicitement dans ce contexte).
def test_real_kernel_with_best_effort_is_rejected_by_construction(real_alpaca_env, real_kernel_process, tmp_path):
    from execution.binder.engine import RealKernelRequiresProofRequired

    pack, closes = _real_pack()
    store = ReceiptStore(tmp_path / "rejected_best_effort.jsonl")
    roster = build_calibrated_trading_agents(pack)
    analysis = NativeRosterAnalysisAdapter(agent_classes=roster)
    bridge = KX108GovernanceBridge(RealKX108Client())
    with pytest.raises(RealKernelRequiresProofRequired):
        CycleEngine(
            market_data=_FakeMarketData(closes), broker=_FakeBroker(), analysis=analysis,
            aggregation=_FakeAggregation(), authority=bridge, symbols=[SYMBOL],
            mode=Mode.PAPER, strategy=_FakeStrategy(), sizing=_FakeSizing(),
            planner=ExecutionPlanner(), proof=store, proof_policy=ProofPolicy.BEST_EFFORT,
        )


# 11. External reste independant : fonctionne SANS aucun CalibrationPack Native
def test_external_path_independent_of_native_calibration_pack(real_alpaca_env, real_kernel_process, tmp_path):
    ds, closes = attempt_real_historical_dataset_with_closes(symbol=SYMBOL, timeframe="1Day", limit=100, lookback_days=150)
    if not ds.is_real:
        pytest.skip("donnees reelles indisponibles")
    store = ReceiptStore(tmp_path / "external_independent.jsonl")
    adapter = ExternalStackAnalysisAdapter(ExampleBrotherStackAdapter())
    bridge = KX108GovernanceBridge(RealKX108Client())
    engine = CycleEngine(
        market_data=_FakeMarketData(closes), broker=_FakeBroker(), analysis=adapter,
        aggregation=_FakeAggregation(), authority=bridge, symbols=[SYMBOL],
        mode=Mode.PAPER, strategy=_FakeStrategy(), sizing=_FakeSizing(),
        planner=ExecutionPlanner(), proof=store, proof_policy=ProofPolicy.REQUIRED,
    )
    outcome = engine.run_cycle()
    assert outcome.decision.authority.value in ("ACT", "HOLD", "BLOCK")


# 18. replay intact (zero appel broker pendant le replay), meme avec un pack calibre
def test_replay_of_calibrated_cycle_has_zero_broker_side_effect(real_alpaca_env, real_kernel_process, tmp_path):
    from proof.receipts.replay import ReplayEngine

    pack, closes = _real_pack()
    store = ReceiptStore(tmp_path / "replay_calibrated.jsonl")
    outcome, broker = _run_calibrated_native_cycle(pack, closes, store)
    calls_before = len(broker.submit_calls)

    replay = ReplayEngine(store)
    stored = store.history()
    assert len(stored) >= 1
    replay.replay_audit(stored[-1].cycle_id)
    assert len(broker.submit_calls) == calls_before  # aucun nouvel appel broker


# 17 (repris ici pour ce module) + Kernel boundary
def test_kernel_files_not_modified_by_calibration_consumption(real_kernel_process):
    result = subprocess.run(["git", "status", "--short"], cwd=str(CORE_REPO),
                             capture_output=True, text=True, check=True)
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    for line in lines:
        assert "merkle_seal.json" in line, f"fichier core modifie de facon inattendue: {line}"


# 19. aucune cle Alpaca dans git status / logs (le fichier .env lui-meme ne
# doit jamais apparaitre — sa valeur n'est jamais lue par ce test).
def test_no_alpaca_env_leak_in_git_status():
    result = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, check=True)
    assert ".env" not in result.stdout
