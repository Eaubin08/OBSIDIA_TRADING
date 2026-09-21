"""
F7 — chaine de receipts : persistance, integrite, frontieres Proof/Authority.

Utilise un CycleEngine reel (F3) branche sur FixtureKX108Client (TEST-ONLY)
et des doubles deterministes, exactement comme tests/integration/
test_paper_execution_pipeline.py (F6) — mais avec `proof=ReceiptStore(...)`
pour exercer la persistance reelle plutot que le chainage en memoire seul.
"""
from __future__ import annotations

import json
import warnings

import pytest

from domain.market import MarketSnapshot
from domain.orders import ExecutionPlan, ExecutionResult
from domain.portfolio import AccountState, PortfolioState
from domain.proposal import ActionProposal, AgentOutput, Consensus, SizingDecision, StrategyCandidate
from domain.receipt import GENESIS_HASH
from domain.types import ActionKind, AssetClass, Authority, DataQuality, Mode, OrderStatus, OrderType, Provenance, Side
from execution.binder.engine import CycleEngine
from execution.binder.planner import ExecutionPlanner
from governance.bridge.governance_bridge import KX108GovernanceBridge
from proof.receipts.receipt_store import DuplicateCycleError, ReceiptStore
from proof.receipts.receipt_verify import IntegrityStatus, ReceiptChainVerifier
from tests.test_support.kx108_fixtures import FixtureKX108Client

SYMBOL = "AAPL"


class FakeMarketData:
    def __init__(self, *, tradable: bool = True, market_open: bool = True):
        self._tradable = tradable
        self._market_open = market_open

    def snapshot(self, symbol):
        return self.snapshots([symbol])[symbol]

    def snapshots(self, symbols):
        return {
            s: MarketSnapshot(
                symbol=s,
                asset_class=AssetClass.EQUITY,
                last_price=100.0,
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
    def __init__(self, *, submit_behavior=None):
        self._submit_behavior = submit_behavior or (lambda plan: self._accepted(plan))
        self.submit_calls = []

    @staticmethod
    def _accepted(plan):
        return ExecutionResult(plan=plan, submitted=True, status=OrderStatus.ACCEPTED,
                                broker_order_id="fake-order-1", mode=Mode.PAPER.value)

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

    def order_status(self, broker_order_id):
        return None

    def order_by_client_order_id(self, client_order_id):
        return None

    def submit(self, plan):
        self.submit_calls.append(plan)
        return self._submit_behavior(plan)

    def cancel(self, plan, broker_order_id):
        raise NotImplementedError

    def replace(self, plan, broker_order_id):
        raise NotImplementedError

    def close_position(self, plan):
        raise NotImplementedError


class FakeAnalysis:
    def analyse(self, symbol, snapshot, portfolio):
        return (
            AgentOutput(
                name="fake-agent", category="test", signal="BUY", confidence=0.9,
                rationale="fixture F7",
                unknowns=("no_order_book_depth",),
                contradictions=("momentum_up_vs_macro_down",),
                risk_flags=("thin_liquidity",),
            ),
        )


class FakeAggregation:
    def aggregate(self, outputs):
        return Consensus(side="BUY", confidence=0.9)


class FakeStrategy:
    def build(self, symbol, snapshot, consensus, portfolio, opportunities=()):
        return (
            StrategyCandidate(symbol=symbol, action=ActionKind.BUY, rationale="fixture F7",
                               confidence=0.9, order_type=OrderType.MARKET, strategy_id="fixture-strategy"),
        )


class FakeSizing:
    def size(self, candidate, snapshot, portfolio):
        return SizingDecision(quantity=1.0, requested_quantity=1.0)


def _make_engine(*, verdict: str, broker: FakeBroker, proof=None, tradable=True):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        kx108 = FixtureKX108Client(verdict=verdict)
    bridge = KX108GovernanceBridge(kx108)
    return CycleEngine(
        market_data=FakeMarketData(tradable=tradable),
        broker=broker,
        analysis=FakeAnalysis(),
        aggregation=FakeAggregation(),
        authority=bridge,
        symbols=[SYMBOL],
        mode=Mode.PAPER,
        strategy=FakeStrategy(),
        sizing=FakeSizing(),
        planner=ExecutionPlanner(),
        proof=proof,
    )


# ── 1. Ecriture puis lecture d'un receipt ──────────────────────────────────


def test_write_then_read_a_receipt(tmp_path):
    store = ReceiptStore(tmp_path / "receipts.jsonl")
    engine = _make_engine(verdict="ACT", broker=FakeBroker(), proof=store)
    outcome = engine.run_cycle()

    stored = store.read(outcome.receipt.decision.decision_id)
    assert stored is not None
    assert stored.cycle_id == outcome.receipt.cycle_id
    assert stored.stored_hash == outcome.receipt.decision_hash()


# ── 2. Plusieurs receipts chaines -> integrite PASS ────────────────────────


def test_multiple_chained_receipts_pass_integrity(tmp_path):
    store = ReceiptStore(tmp_path / "receipts.jsonl")
    broker = FakeBroker()
    for verdict in ("HOLD", "BLOCK", "ACT"):
        _make_engine(verdict=verdict, broker=broker, proof=store).run_cycle()

    report = ReceiptChainVerifier().verify_store(store)
    assert report.status == IntegrityStatus.VALID
    assert report.checked_count == 3
    assert store.last_hash() != GENESIS_HASH


# ── 3. Modification d'un ancien receipt -> integrite FAIL ──────────────────


def test_tampering_with_an_old_receipt_fails_integrity(tmp_path):
    path = tmp_path / "receipts.jsonl"
    store = ReceiptStore(path)
    broker = FakeBroker()
    _make_engine(verdict="HOLD", broker=broker, proof=store).run_cycle()
    _make_engine(verdict="ACT", broker=broker, proof=store).run_cycle()

    lines = path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[0])
    tampered["receipt"]["decision"]["authority"] = "ACT"  # BLOCK->ACT falsifie
    lines[0] = json.dumps(tampered)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = ReceiptChainVerifier().verify_store(store)
    assert report.status == IntegrityStatus.CORRUPTED
    assert "altere" in report.first_error
    assert report.first_error_index == 0


# ── 4. Suppression d'un receipt intermediaire -> FAIL ──────────────────────


def test_removing_a_middle_receipt_fails_integrity(tmp_path):
    path = tmp_path / "receipts.jsonl"
    store = ReceiptStore(path)
    broker = FakeBroker()
    for verdict in ("HOLD", "BLOCK", "ACT"):
        _make_engine(verdict=verdict, broker=broker, proof=store).run_cycle()

    lines = path.read_text(encoding="utf-8").splitlines()
    del lines[1]  # retire le receipt du milieu
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = ReceiptChainVerifier().verify_store(store)
    assert report.status == IntegrityStatus.CORRUPTED
    assert "rupture de chaine" in report.first_error


# ── 5. Mauvais previous_hash -> FAIL ────────────────────────────────────────


def test_bad_previous_hash_fails_integrity(tmp_path):
    path = tmp_path / "receipts.jsonl"
    store = ReceiptStore(path)
    _make_engine(verdict="HOLD", broker=FakeBroker(), proof=store).run_cycle()

    lines = path.read_text(encoding="utf-8").splitlines()
    payload = json.loads(lines[0])
    payload["receipt"]["previous_receipt_hash"] = "f" * 64
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    report = ReceiptChainVerifier().verify_store(store)
    assert report.status == IntegrityStatus.CORRUPTED


# ── 6. Duplicate cycle_id -> refus explicite ────────────────────────────────


def test_duplicate_cycle_id_is_rejected(tmp_path):
    store = ReceiptStore(tmp_path / "receipts.jsonl")
    engine = _make_engine(verdict="HOLD", broker=FakeBroker(), proof=None)
    outcome = engine.run_cycle()

    store.record(outcome.receipt)
    with pytest.raises(DuplicateCycleError):
        store.record(outcome.receipt)  # meme cycle_id, deuxieme tentative


# ── 7. JSON malforme -> erreur explicite ────────────────────────────────────


def test_malformed_json_line_raises_explicit_error(tmp_path):
    path = tmp_path / "receipts.jsonl"
    store = ReceiptStore(path)
    _make_engine(verdict="HOLD", broker=FakeBroker(), proof=store).run_cycle()
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not valid json\n")

    report = ReceiptChainVerifier().verify_store(store)
    assert report.status == IntegrityStatus.CORRUPTED
    assert "illisible" in report.first_error or "JSON" in report.first_error


# ── 8. Chaine vide -> comportement documente ────────────────────────────────


def test_empty_chain_is_explicitly_reported(tmp_path):
    store = ReceiptStore(tmp_path / "receipts.jsonl")
    report = ReceiptChainVerifier().verify_store(store)
    assert report.status == IntegrityStatus.EMPTY
    assert report.is_valid  # une chaine vide n'est pas "corrompue"
    assert store.last_hash() == GENESIS_HASH


# ── 9. Restart du processus -> reprise correcte de la tete de chaine ───────


def test_restart_resumes_chain_head_correctly(tmp_path):
    path = tmp_path / "receipts.jsonl"
    store_1 = ReceiptStore(path)
    broker = FakeBroker()
    _make_engine(verdict="HOLD", broker=broker, proof=store_1).run_cycle()
    head_before_restart = store_1.last_hash()

    store_2 = ReceiptStore(path)  # nouvelle instance, meme fichier ("restart du processus")
    assert store_2.last_hash() == head_before_restart

    _make_engine(verdict="ACT", broker=broker, proof=store_2).run_cycle()
    report = ReceiptChainVerifier().verify_store(store_2)
    assert report.status == IntegrityStatus.VALID
    assert report.checked_count == 2


# ── Frontieres non negociables ───────────────────────────────────────────


def test_proof_is_not_authority():
    """ReceiptStore/ReceiptChainVerifier n'ont aucune methode produisant une Authority/Decision."""
    import inspect

    from proof.receipts import receipt_store, receipt_verify

    for module in (receipt_store, receipt_verify):
        source = inspect.getsource(module)
        assert "Authority(" not in source
        assert "Decision(" not in source
        assert "return Authority" not in source


def test_replay_has_no_broker_or_binder_import():
    """Replay != Execution : aucune LIGNE D'IMPORT broker/execution dans replay.py.

    On ne cherche que dans les lignes `import`/`from ... import`, pas dans le
    texte des docstrings (qui mentionnent volontairement ces noms pour
    documenter l'interdiction elle-meme).
    """
    import inspect

    from proof.receipts import replay as replay_module

    import_lines = [
        line.strip()
        for line in inspect.getsource(replay_module).splitlines()
        if line.strip().startswith("import ") or line.strip().startswith("from ")
    ]
    joined = "\n".join(import_lines)
    assert "market.adapters" not in joined
    assert "execution.binder.paper_execution" not in joined


def test_persisting_a_receipt_never_changes_its_decision(tmp_path):
    """Receipt != Decision : persister ne peut jamais modifier retroactivement l'autorite deja produite."""
    store = ReceiptStore(tmp_path / "receipts.jsonl")
    engine = _make_engine(verdict="BLOCK", broker=FakeBroker(), proof=store)
    outcome = engine.run_cycle()

    original_authority = outcome.decision.authority
    # outcome.receipt a deja ete persiste par le moteur via proof= pendant run_cycle
    # (CycleEngine._prove appelle self.proof.record(receipt)) : on relit simplement.

    stored = store.read(outcome.receipt.decision.decision_id)
    assert stored.authority == original_authority.value
    assert outcome.decision.authority == original_authority  # inchange par la persistance
