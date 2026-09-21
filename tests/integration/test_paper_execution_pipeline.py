"""
F6 — Execution/Binder avec Alpaca PAPER : tests de cablage et de frontiere.

Ces tests exercent le CycleEngine reel (execution/binder/engine.py, F3) avec
un KX108GovernanceBridge reel (F5) branche sur FixtureKX108Client (TEST-ONLY,
tests/test_support/kx108_fixtures.py) et un broker Alpaca FAKE (spy, pas de
reseau). L'objectif n'est pas de retester le roster de 17 agents (deja
couvert par tests/unit/test_native_roster.py) ni la logique Alpaca HTTP
(deja couverte par tests/unit/test_alpaca_providers.py), mais de prouver que
le chemin Bridge -> Binder -> Broker respecte les invariants de gouvernance
de bout en bout. Les etapes d'analyse/strategie/dimensionnement sont donc
des doubles deterministes, choix documente ici plutot que dans un
commentaire disperse.
"""
from __future__ import annotations

import warnings

import pytest

from domain.market import MarketSnapshot
from domain.orders import ExecutionPlan
from domain.portfolio import AccountState, PortfolioState
from domain.proposal import AgentOutput, Consensus, SizingDecision, StrategyCandidate
from domain.receipt import Decision
from domain.state import TradingDomainState
from domain.types import ActionKind, AssetClass, Authority, DataQuality, Mode, OrderType, Provenance, Side
from execution.binder.engine import CycleEngine
from execution.binder.order_ledger_jsonl import JsonlOrderLedger
from execution.binder.paper_execution import LiveModeRejected, require_paper_mode
from execution.binder.planner import ExecutionPlanner
from governance.bridge.governance_bridge import KX108GovernanceBridge
from market.adapters.alpaca.alpaca_config import AlpacaConfig
from tests.test_support.kx108_fixtures import FixtureKX108Client

SYMBOL = "AAPL"


# ── Doubles deterministes (pas de reseau, pas d'agents reels) ──────────────


class FakeMarketData:
    def __init__(self, *, tradable: bool = True, market_open: bool = True, last_price: float = 100.0):
        self._tradable = tradable
        self._market_open = market_open
        self._last_price = last_price

    def snapshot(self, symbol: str) -> MarketSnapshot:
        return self.snapshots([symbol])[symbol]

    def snapshots(self, symbols):
        return {
            s: MarketSnapshot(
                symbol=s,
                asset_class=AssetClass.EQUITY,
                last_price=self._last_price,
                provenance=Provenance(source="fake", fetched_at=0.0, quality=DataQuality.LIVE, mode=Mode.PAPER),
                tradable=self._tradable,
                market_open=self._market_open,
            )
            for s in symbols
        }

    def history(self, symbol, limit=200):
        return ()

    def context(self):
        return None


class FakeBroker:
    """Spy BrokerPort : jamais de reseau, comportement controle par le test."""

    def __init__(self, *, trading_blocked: bool = False, submit_behavior=None):
        self._trading_blocked = trading_blocked
        self._submit_behavior = submit_behavior or (lambda plan: _accepted_result(plan))
        self.submit_calls = []

    def account(self) -> AccountState:
        return AccountState(
            equity=100_000.0,
            cash=100_000.0,
            buying_power=100_000.0,
            provenance=Provenance(source="fake", fetched_at=0.0, quality=DataQuality.LIVE, mode=Mode.PAPER),
            trading_blocked=self._trading_blocked,
        )

    def positions(self):
        return ()

    def open_orders(self):
        return ()

    def portfolio(self) -> PortfolioState:
        return PortfolioState(account=self.account())

    def order_status(self, broker_order_id):
        return None

    def order_by_client_order_id(self, client_order_id):
        return None

    def submit(self, plan: ExecutionPlan):
        self.submit_calls.append(plan)
        return self._submit_behavior(plan)

    def cancel(self, plan, broker_order_id):
        raise NotImplementedError

    def replace(self, plan, broker_order_id):
        raise NotImplementedError

    def close_position(self, plan):
        raise NotImplementedError


def _accepted_result(plan: ExecutionPlan):
    from domain.orders import ExecutionResult
    from domain.types import OrderStatus

    return ExecutionResult(
        plan=plan,
        submitted=True,
        status=OrderStatus.ACCEPTED,
        broker_order_id="fake-order-1",
        mode=Mode.PAPER.value,
    )


class FakeAnalysis:
    """Un seul AgentOutput factice — le contenu du vote n'est pas ce qui est teste ici."""

    def analyse(self, symbol, snapshot, portfolio):
        return (
            AgentOutput(
                name="fake-agent",
                category="test",
                signal="BUY",
                confidence=0.9,
                rationale="fixture F6",
            ),
        )


class FakeAggregation:
    def aggregate(self, outputs):
        return Consensus(side="BUY", confidence=0.9)


class FakeStrategy:
    def build(self, symbol, snapshot, consensus, portfolio, opportunities=()):
        return (
            StrategyCandidate(
                symbol=symbol,
                action=ActionKind.BUY,
                rationale="fixture F6",
                confidence=0.9,
                order_type=OrderType.MARKET,
                strategy_id="fixture-strategy",
            ),
        )


class FakeSizing:
    def __init__(self, quantity: float = 1.0):
        self._quantity = quantity

    def size(self, candidate, snapshot, portfolio):
        return SizingDecision(quantity=self._quantity, requested_quantity=self._quantity)


def _make_engine(*, verdict: str, broker: FakeBroker, order_ledger=None, tradable=True, market_open=True, sizing_qty=1.0):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # avertissement TEST-ONLY attendu, pas une erreur
        kx108 = FixtureKX108Client(verdict=verdict)
    bridge = KX108GovernanceBridge(kx108)
    return CycleEngine(
        market_data=FakeMarketData(tradable=tradable, market_open=market_open),
        broker=broker,
        analysis=FakeAnalysis(),
        aggregation=FakeAggregation(),
        authority=bridge,
        symbols=[SYMBOL],
        mode=Mode.PAPER,
        strategy=FakeStrategy(),
        sizing=FakeSizing(sizing_qty),
        planner=ExecutionPlanner(),
        order_ledger=order_ledger,
    )


# ── 1-2. BLOCK / HOLD -> aucune execution ──────────────────────────────────


@pytest.mark.parametrize("verdict", ["BLOCK", "HOLD"])
def test_block_or_hold_verdict_never_reaches_broker(verdict):
    broker = FakeBroker()
    engine = _make_engine(verdict=verdict, broker=broker)
    outcome = engine.run_cycle()

    assert outcome.decision.authority is (Authority.BLOCK if verdict == "BLOCK" else Authority.HOLD)
    assert outcome.plan is None
    assert outcome.execution is None
    assert broker.submit_calls == []
    assert outcome.touched_the_market is False
    assert outcome.receipt is not None  # ACT/HOLD/BLOCK produisent tous un receipt


# ── 3. ACT + Binder refuse (etat degrade) -> aucune execution ──────────────


def test_act_verdict_with_degraded_state_still_refuses_execution():
    broker = FakeBroker(trading_blocked=True)  # compte bloque -> can_support_irreversible_action=False
    engine = _make_engine(verdict="ACT", broker=broker)
    outcome = engine.run_cycle()

    assert outcome.decision.authority is Authority.ACT
    assert outcome.plan is None  # planner refuse : etat ne supporte pas d'action irreversible
    assert outcome.execution is None
    assert broker.submit_calls == []
    assert outcome.touched_the_market is False


# ── 4. ACT + Binder autorise -> ordre PAPER uniquement ─────────────────────


def test_act_verdict_with_supported_state_submits_paper_order_only():
    broker = FakeBroker()
    engine = _make_engine(verdict="ACT", broker=broker)
    outcome = engine.run_cycle()

    assert outcome.decision.authority is Authority.ACT
    assert outcome.plan is not None
    assert len(broker.submit_calls) == 1
    assert outcome.execution.submitted is True
    assert outcome.touched_the_market is True
    # Le mode transmis au broker est celui du moteur : jamais autre chose que PAPER ici.
    assert engine.mode is Mode.PAPER


# ── 5. Tentative de configuration LIVE -> refus structurel ─────────────────


def test_require_paper_mode_rejects_live_configuration():
    live_config = AlpacaConfig(
        mode=Mode.LIVE,
        api_key="x",
        secret_key="y",
        trading_base_url="https://api.alpaca.markets",
    )
    with pytest.raises(LiveModeRejected):
        require_paper_mode(live_config)


def test_require_paper_mode_accepts_paper_configuration():
    paper_config = AlpacaConfig(
        mode=Mode.PAPER,
        api_key="x",
        secret_key="y",
        trading_base_url="https://paper-api.alpaca.markets",
    )
    require_paper_mode(paper_config)  # ne leve rien


# ── 6. Compte/permission invalide cote Alpaca -> refus, aucun ordre ────────


def test_broker_permission_denied_blocks_before_submission():
    broker = FakeBroker(trading_blocked=True)
    engine = _make_engine(verdict="ACT", broker=broker)
    outcome = engine.run_cycle()

    assert broker.submit_calls == []
    assert outcome.execution is None


# ── 7. Erreur Alpaca a la soumission -> echec explicite, jamais faux succes ─


def test_alpaca_submission_error_produces_explicit_failure_never_false_success():
    def failing_submit(plan):
        raise RuntimeError("Alpaca 500: internal error")

    broker = FakeBroker(submit_behavior=failing_submit)
    engine = _make_engine(verdict="ACT", broker=broker)
    outcome = engine.run_cycle()

    assert len(broker.submit_calls) == 1  # la tentative a bien eu lieu
    assert outcome.execution is not None
    assert outcome.execution.submitted is False
    assert outcome.touched_the_market is False
    assert "echec de soumission" in (outcome.execution.rejected_reason or "")


# ── 8. Double soumission du meme TradeIntent -> protection idempotence ─────


def test_duplicate_execution_plan_is_blocked_by_order_ledger(tmp_path):
    broker = FakeBroker()
    ledger = JsonlOrderLedger(tmp_path / "ledger.jsonl")

    proposal_consensus = Consensus(side="BUY", confidence=0.9)
    sizing = SizingDecision(quantity=1.0, requested_quantity=1.0)
    from domain.proposal import ActionProposal

    proposal = ActionProposal(
        symbol=SYMBOL, action=ActionKind.BUY, consensus=proposal_consensus, sizing=sizing
    )
    decision = Decision(decision_id="d-fixed-0001", authority=Authority.ACT, reason="test", proposal=proposal)
    plan = ExecutionPlan(
        decision_id=decision.decision_id,
        symbol=SYMBOL,
        action=ActionKind.BUY,
        side=Side.BUY,
        quantity=1.0,
        order_type=OrderType.MARKET,
        authority=Authority.ACT,
        client_order_id="obsidia-d-fixed-0001",
    )

    engine = _make_engine(verdict="ACT", broker=broker, order_ledger=ledger)
    result_1 = engine._execute("cycle-1", decision, plan, lambda msg: None)
    result_2 = engine._execute("cycle-2", decision, plan, lambda msg: None)  # meme plan, deuxieme tentative

    assert result_1.submitted is True
    assert result_2.submitted is False
    assert "idempotence" in (result_2.rejected_reason or "")
    assert len(broker.submit_calls) == 1  # le broker n'a ete appele qu'une seule fois


# ── 9. Provenance du verdict KX108 conservee jusqu'au receipt ──────────────


def test_kx108_verdict_provenance_survives_to_receipt():
    broker = FakeBroker()
    engine = _make_engine(verdict="ACT", broker=broker)
    outcome = engine.run_cycle()

    receipt_dict = outcome.receipt.as_dict()
    kx108_response = receipt_dict["decision"]["metrics"]["kx108_response"]
    assert kx108_response["source"] == "FixtureKX108Client (TEST-ONLY)"
    assert kx108_response["verdict"] == "ACT"


# ── 10. Aucun chemin direct agent/simulation/adapter -> Alpaca ─────────────


def test_no_direct_import_of_alpaca_outside_execution_assembly_point():
    """
    Verification statique : seul execution/ (le point d'assemblage F6) peut
    importer market.adapters.alpaca. native/, simulation/ et governance/
    n'en ont structurellement pas besoin (deja verifie separement pour
    simulation/ en F4) — ce test couvre native/ et governance/ pour F6.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[2]
    forbidden_pattern = re.compile(r"\bmarket\.adapters\.alpaca\b")
    offending = []
    for base in ("native", "governance", "domain"):
        for path in (root / base).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if forbidden_pattern.search(text):
                offending.append(str(path))
    assert offending == [], f"import direct interdit vers market.adapters.alpaca trouve dans: {offending}"


# ── Isolation du fixture KX108 : jamais chargeable en configuration prod ───


def test_fixture_client_not_loadable_from_production_config():
    """
    Preuve que FixtureKX108Client ne peut pas etre atteint depuis un chemin
    de configuration production : ni .env.example, ni AlpacaConfig, ni
    governance/bridge/, ni execution/binder/paper_execution.py ne le
    referencent. Seul un import EXPLICITE depuis tests/ y donne acces.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[2]
    # On cherche un IMPORT ou une INSTANCIATION reels, pas une simple mention
    # documentaire (ce module lui-meme explique en prose, dans son docstring,
    # pourquoi ne jamais faire cet import — ce qui ne doit pas se declencher
    # comme un faux positif ici).
    forbidden_import = re.compile(
        r"^\s*(from\s+tests(\.|(\s+import))|import\s+tests\b)", re.MULTILINE
    )
    forbidden_instantiation = re.compile(r"\bFixtureKX108Client\s*\(|\bStaticKX108TestClient\s*\(")
    production_dirs = ("governance", "execution", "market", "native", "domain")
    offending = []
    for base in production_dirs:
        for path in (root / base).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if forbidden_import.search(text) or forbidden_instantiation.search(text):
                offending.append(str(path))

    env_example = root / ".env.example"
    if env_example.exists() and re.search(
        r"FixtureKX108Client|StaticKX108TestClient", env_example.read_text(encoding="utf-8")
    ):
        offending.append(str(env_example))

    assert offending == [], (
        f"import/instanciation reels de FixtureKX108Client/tests.test_support "
        f"trouves dans du code production: {offending}"
    )

    # Le point d'assemblage production n'a par ailleurs aucun defaut qui
    # construirait un FixtureKX108Client : build_paper_cycle_engine exige un
    # kx108_client explicite, sans valeur par defaut.
    import inspect

    from execution.binder.paper_execution import build_paper_cycle_engine

    signature = inspect.signature(build_paper_cycle_engine)
    assert signature.parameters["kx108_client"].default is inspect.Parameter.empty
