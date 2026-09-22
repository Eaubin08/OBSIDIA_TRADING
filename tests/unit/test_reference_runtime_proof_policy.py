"""
F12.1 — Reference Runtime Closure.

Garantit PAR CONSTRUCTION (pas par convention documentaire) que
`RealKX108Client` (vrai Kernel X-108, F12) n'est jamais associe
implicitement a `ProofPolicy.BEST_EFFORT`. `ProofPolicy.BEST_EFFORT` reste
le defaut historique pour tout le reste (Fixture/Unavailable/Static +
tests/demo) : ce module verifie que rien de ca n'a ete casse.
"""
from __future__ import annotations

import pytest

from domain.market import Bar, MarketSnapshot
from domain.orders import ExecutionPlan
from domain.portfolio import AccountState, PortfolioState
from domain.proposal import Consensus, StrategyCandidate, SizingDecision
from domain.types import ActionKind, AssetClass, DataQuality, Mode, OrderType, Provenance
from execution.binder.engine import CycleEngine, RealKernelRequiresProofRequired
from execution.binder.planner import ExecutionPlanner
from execution.binder.proof_policy import ProofPolicy
from governance.bridge.governance_bridge import KX108GovernanceBridge
from governance.bridge.kx108_client import (
    RaisingKX108Client,
    RealKX108Client,
    StaticKX108Client,
    UnavailableKX108Client,
)
from proof.receipts.receipt_store import ReceiptStore

SYMBOL = "AAPL"


def _bars() -> tuple:
    return (
        Bar(timestamp=0.0, open=100.0, high=100.5, low=99.5, close=100.0, volume=1_000.0),
    )


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
            broker_order_id="f12-1-test", client_order_id=plan.client_order_id,
            symbol=plan.symbol, side=plan.side, quantity=plan.quantity, order_type=plan.order_type,
            status=OrderStatus.FILLED, filled_quantity=plan.quantity, filled_avg_price=100.0,
            submitted_at=0.0, updated_at=0.0,
        )


class _NoOpAnalysis:
    def analyse(self, symbol, snapshot, portfolio):
        return ()


class _FakeAggregation:
    def aggregate(self, outputs):
        return Consensus(side="BUY", confidence=0.6, buy_weight=1.0)


class _FakeStrategy:
    def propose(self, state):
        return StrategyCandidate(
            symbol=SYMBOL, action=ActionKind.BUY, rationale="F12.1 test",
            confidence=0.6, order_type=OrderType.MARKET, strategy_id="f12-1-test",
        )


class _FakeSizing:
    def size(self, candidate, snapshot, portfolio):
        return SizingDecision(quantity=1.0, requested_quantity=1.0)


def _build_engine(*, kx108_client, proof_policy, proof=None):
    bridge = KX108GovernanceBridge(kx108_client)
    broker = _FakeBroker()
    return CycleEngine(
        market_data=_FakeMarketData(), broker=broker, analysis=_NoOpAnalysis(),
        aggregation=_FakeAggregation(), authority=bridge, symbols=[SYMBOL],
        mode=Mode.PAPER, strategy=_FakeStrategy(), sizing=_FakeSizing(),
        planner=ExecutionPlanner(), proof=proof, proof_policy=proof_policy,
    ), broker


# ── 1. Reference runtime + RealKX108Client => PROOF_REQUIRED accepte ────────

def test_reference_runtime_real_kernel_with_required_is_accepted(tmp_path):
    store = ReceiptStore(tmp_path / "receipts.jsonl")
    engine, _broker = _build_engine(
        kx108_client=RealKX108Client(base_url="http://127.0.0.1:1"),  # injoignable, mais construction seule testee ici
        proof_policy=ProofPolicy.REQUIRED,
        proof=store,
    )
    assert engine.proof_policy is ProofPolicy.REQUIRED


# ── 2. Aucune configuration implicite Real Kernel + BEST_EFFORT ─────────────

def test_real_kernel_with_best_effort_is_rejected_at_construction():
    with pytest.raises(RealKernelRequiresProofRequired):
        _build_engine(
            kx108_client=RealKX108Client(base_url="http://127.0.0.1:1"),
            proof_policy=ProofPolicy.BEST_EFFORT,
        )


def test_real_kernel_with_default_proof_policy_is_rejected():
    """Le defaut de CycleEngine reste BEST_EFFORT (retro-compatibilite) ;
    ne pas le passer explicitement avec RealKX108Client doit donc echouer
    exactement comme le passer explicitement — pas de trou silencieux."""
    bridge = KX108GovernanceBridge(RealKX108Client(base_url="http://127.0.0.1:1"))
    broker = _FakeBroker()
    with pytest.raises(RealKernelRequiresProofRequired):
        CycleEngine(
            market_data=_FakeMarketData(), broker=broker, analysis=_NoOpAnalysis(),
            aggregation=_FakeAggregation(), authority=bridge, symbols=[SYMBOL],
            mode=Mode.PAPER, strategy=_FakeStrategy(), sizing=_FakeSizing(),
            planner=ExecutionPlanner(),
            # proof_policy volontairement omis : doit retomber sur BEST_EFFORT et donc echouer.
        )


# ── 3. BEST_EFFORT reste disponible pour les autres clients (non casse) ─────

@pytest.mark.parametrize(
    "kx108_client",
    [
        UnavailableKX108Client(),
        StaticKX108Client({"verdict": "HOLD"}),
        RaisingKX108Client(RuntimeError("boom")),
    ],
)
def test_best_effort_still_works_for_non_real_kernel_clients(kx108_client):
    engine, _broker = _build_engine(kx108_client=kx108_client, proof_policy=ProofPolicy.BEST_EFFORT)
    assert engine.proof_policy is ProofPolicy.BEST_EFFORT
    # Le cycle doit pouvoir tourner sans lever RealKernelRequiresProofRequired.
    outcome = engine.run_cycle()
    assert outcome.decision is not None


# ── 9. Native et External passent par la meme contrainte (meme fonction) ────

def test_native_and_external_share_the_same_construction_guard():
    """Le garde-fou vit dans CycleEngine.__init__, en amont de tout choix
    d'AnalysisPort (Native vs External) : les deux chemins sont donc soumis
    a exactement la meme regle, sans code duplique."""
    import inspect

    from execution.binder import engine as engine_module

    source = inspect.getsource(engine_module._reject_implicit_best_effort_with_real_kernel)
    # Une seule implementation ; aucune trace de branchement Native/External
    # dans le garde-fou lui-meme (il ne connait que authority/proof_policy).
    assert "native" not in source.lower()
    assert "external" not in source.lower()


# ── 10. Aucun fichier Kernel modifie (verification structurelle locale) ─────

def test_engine_guard_never_imports_kernel_core_paths():
    """Le garde-fou F12.1 ne touche qu'a governance/bridge/ (deja Trading-side) ;
    aucune reference a un chemin du core Obsidia ou au Kernel lui-meme."""
    import inspect

    from execution.binder import engine as engine_module

    source = inspect.getsource(engine_module)
    assert "obsidia-x108-proofs" not in source
    assert "server.kernel" not in source
