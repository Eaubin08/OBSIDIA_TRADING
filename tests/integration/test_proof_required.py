"""
F11 — PROOF_REQUIRED : tests de la politique de preuve.

Reutilise les doubles deterministes de test_paper_execution_pipeline.py
(FakeMarketData, FakeBroker, FakeAnalysis, FakeAggregation, FakeStrategy,
FakeSizing) plutot que de les dupliquer. Objectif : prouver que

  - un port de preuve injoignable AVANT tout appel broker bloque
    l'execution sous ProofPolicy.REQUIRED (jamais sous BEST_EFFORT) ;
  - un succes broker + echec de persistance finale n'est jamais presente
    comme un succes propre ni comme un echec d'execution
    (ProofOutcome.EXECUTION_SUCCEEDED_PROOF_INCOMPLETE) ;
  - un receipt jamais persiste ne fait jamais avancer la chaine en memoire
    (le prochain receipt reellement ecrit chaine sur le dernier hash
    REELLEMENT dans le store, pas sur un fantome) ;
  - rien de tout cela ne change qui decide (KX108) ni qui execute (Binder) :
    proof != authority.
"""
from __future__ import annotations

import warnings

import pytest

from domain.receipt import GENESIS_HASH
from domain.types import Authority, Mode
from execution.binder.engine import CycleEngine
from execution.binder.planner import ExecutionPlanner
from execution.binder.proof_policy import ProofOutcome, ProofPolicy
from governance.bridge.governance_bridge import KX108GovernanceBridge
from proof.receipts.receipt_verify import ReceiptChainVerifier
from proof.receipts.receipt_store import ReceiptStore
from tests.test_support.kx108_fixtures import FixtureKX108Client
from tests.integration.test_paper_execution_pipeline import (
    FakeAggregation,
    FakeAnalysis,
    FakeBroker,
    FakeMarketData,
    FakeSizing,
    FakeStrategy,
    SYMBOL,
)


class RaisingProofStore:
    """
    Double ProofPort : `last_hash()` reussit (chaine deja etablie), mais
    `record()` echoue TOUJOURS — simule une persistance indisponible au
    moment d'ecrire, apres que le broker ait deja pu etre contacte.
    """

    def __init__(self, seed_last_hash: str = GENESIS_HASH):
        self._last_hash = seed_last_hash

    def last_hash(self) -> str:
        return self._last_hash

    def record(self, receipt):
        raise RuntimeError("proof store indisponible a l'ecriture")

    def read(self, decision_id):
        return None

    def history(self, limit: int = 100):
        return ()


class UnreachableProofStore:
    """
    Double ProofPort : joignable UNE fois (le sondage fait par
    `CycleEngine.__init__` pour amorcer la chaine en memoire reussit),
    puis injoignable ensuite — simule une panne survenant apres le
    demarrage du moteur mais avant qu'un cycle ne tente d'executer.
    """

    def __init__(self):
        self._calls = 0

    def last_hash(self) -> str:
        self._calls += 1
        if self._calls == 1:
            return GENESIS_HASH
        raise RuntimeError("proof store injoignable")

    def record(self, receipt):
        raise RuntimeError("proof store injoignable")

    def read(self, decision_id):
        return None

    def history(self, limit: int = 100):
        return ()


def _make_engine(
    *,
    verdict: str,
    broker: FakeBroker,
    proof=None,
    proof_policy: ProofPolicy = ProofPolicy.BEST_EFFORT,
    tradable: bool = True,
):
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
        sizing=FakeSizing(1.0),
        planner=ExecutionPlanner(),
        proof=proof,
        proof_policy=proof_policy,
    )


# ── 1-2. HOLD / BLOCK -> aucun broker, receipt/proof coherent ──────────────


@pytest.mark.parametrize("verdict", ["HOLD", "BLOCK"])
def test_hold_or_block_never_touches_broker_even_with_real_proof_store(verdict, tmp_path):
    broker = FakeBroker()
    store = ReceiptStore(tmp_path / "receipts.jsonl")
    engine = _make_engine(verdict=verdict, broker=broker, proof=store)
    outcome = engine.run_cycle()

    assert broker.submit_calls == []
    assert outcome.touched_the_market is False
    assert outcome.receipt is not None
    assert outcome.proof_outcome is ProofOutcome.PROVEN
    assert store.read(outcome.decision.decision_id) is not None


# ── 3. ACT + Binder refuse -> aucun broker ──────────────────────────────────


def test_act_with_binder_refusal_never_touches_broker(tmp_path):
    broker = FakeBroker(trading_blocked=True)
    store = ReceiptStore(tmp_path / "receipts.jsonl")
    engine = _make_engine(verdict="ACT", broker=broker, proof=store)
    outcome = engine.run_cycle()

    assert broker.submit_calls == []
    assert outcome.execution is None
    assert outcome.proof_outcome is ProofOutcome.PROVEN


# ── 4. ACT + proof indisponible AVANT execution -> aucun broker ────────────


def test_act_with_unreachable_proof_before_execution_blocks_under_required_policy():
    broker = FakeBroker()
    engine = _make_engine(
        verdict="ACT",
        broker=broker,
        proof=UnreachableProofStore(),
        proof_policy=ProofPolicy.REQUIRED,
    )
    outcome = engine.run_cycle()

    assert broker.submit_calls == [], "REQUIRED doit bloquer avant tout appel broker"
    assert outcome.execution is not None
    assert outcome.execution.submitted is False
    assert "PROOF_REQUIRED" in (outcome.execution.rejected_reason or "")


def test_act_with_unreachable_proof_before_execution_does_not_block_under_best_effort():
    """BEST_EFFORT ne verifie pas la joignabilite du store avant execution :
    seul REQUIRED introduit cette barriere (voir proof_policy.py)."""
    broker = FakeBroker()
    engine = _make_engine(
        verdict="ACT",
        broker=broker,
        proof=UnreachableProofStore(),
        proof_policy=ProofPolicy.BEST_EFFORT,
    )
    outcome = engine.run_cycle()

    assert len(broker.submit_calls) == 1
    assert outcome.touched_the_market is True


# ── 5. ACT + proof pre-execution OK + broker succes + preuve finale OK ─────


def test_act_full_success_is_proven_end_to_end(tmp_path):
    broker = FakeBroker()
    store = ReceiptStore(tmp_path / "receipts.jsonl")
    engine = _make_engine(
        verdict="ACT", broker=broker, proof=store, proof_policy=ProofPolicy.REQUIRED
    )
    outcome = engine.run_cycle()

    assert len(broker.submit_calls) == 1
    assert outcome.touched_the_market is True
    assert outcome.proof_outcome is ProofOutcome.PROVEN
    assert store.read(outcome.decision.decision_id) is not None


# ── 6. ACT + proof pre-execution OK + broker failure -> echec durablement prouve ─


def test_act_broker_failure_is_durably_proven_never_false_success(tmp_path):
    def failing_submit(plan):
        raise RuntimeError("Alpaca 500")

    broker = FakeBroker(submit_behavior=failing_submit)
    store = ReceiptStore(tmp_path / "receipts.jsonl")
    engine = _make_engine(
        verdict="ACT", broker=broker, proof=store, proof_policy=ProofPolicy.REQUIRED
    )
    outcome = engine.run_cycle()

    assert outcome.execution.submitted is False
    assert outcome.touched_the_market is False
    assert outcome.proof_outcome is ProofOutcome.PROVEN  # l'echec lui-meme est prouve
    stored = store.read(outcome.decision.decision_id)
    assert stored is not None
    assert stored.raw["execution_result"]["submitted"] is False


# ── 7. ACT + broker succes + preuve finale ECHOUE -> jamais un succes normal ─


def test_act_broker_success_with_proof_persistence_failure_is_never_a_clean_success():
    broker = FakeBroker()
    proof = RaisingProofStore()
    engine = _make_engine(verdict="ACT", broker=broker, proof=proof)
    outcome = engine.run_cycle()

    # Le broker a bel et bien ete contacte et a accepte l'ordre : on ne peut
    # pas pretendre que "rien ne s'est passe".
    assert len(broker.submit_calls) == 1
    assert outcome.touched_the_market is True
    # Mais ce n'est jamais presente comme un succes propre non plus.
    assert outcome.proof_outcome is ProofOutcome.EXECUTION_SUCCEEDED_PROOF_INCOMPLETE
    assert outcome.proof_outcome is not ProofOutcome.PROVEN


def test_hold_with_proof_persistence_failure_is_marked_incomplete_not_execution_related():
    broker = FakeBroker()
    proof = RaisingProofStore()
    engine = _make_engine(verdict="HOLD", broker=broker, proof=proof)
    outcome = engine.run_cycle()

    assert broker.submit_calls == []
    assert outcome.touched_the_market is False
    assert outcome.proof_outcome is ProofOutcome.ABSTENTION_PROOF_INCOMPLETE


# ── chaine : un receipt jamais persiste ne fait jamais avancer la chaine ──


def test_unpersisted_receipt_never_advances_the_in_memory_chain_pointer(tmp_path):
    """
    Sequence : 1er cycle echoue a se persister (proof store en panne
    temporaire), 2e cycle avec un vrai store reussit. Le 2e receipt doit
    chainer sur GENESIS_HASH (rien n'a jamais ete ecrit avant lui), pas sur
    le hash du 1er receipt fantome — sinon `verify_chain` signalerait une
    rupture qui n'a jamais existe dans le store reel.
    """
    store_path = tmp_path / "receipts.jsonl"
    broker = FakeBroker()

    failing_engine = _make_engine(verdict="HOLD", broker=broker, proof=RaisingProofStore())
    failed_outcome = failing_engine.run_cycle()
    assert failed_outcome.proof_outcome is ProofOutcome.ABSTENTION_PROOF_INCOMPLETE

    store = ReceiptStore(store_path)
    ok_engine = _make_engine(verdict="HOLD", broker=broker, proof=store)
    ok_outcome = ok_engine.run_cycle()
    assert ok_outcome.proof_outcome is ProofOutcome.PROVEN

    history = store.history()
    assert len(history) == 1
    assert history[0].previous_receipt_hash == GENESIS_HASH

    result = ReceiptChainVerifier().verify_store(store)
    assert result.status.name == "VALID"


# ── 8-13 : couverts par les tests existants F6/F7/F8.5/F8.6 (reutilises, ──
# pas dupliques) : idempotence (test_duplicate_execution_plan_is_blocked_
# by_order_ledger), replay sans side effect (test_end_to_end_full_stack.py
# / test_end_to_end_external_full_stack.py), hash-chain et alteration
# (test_receipt_chain.py), Native/External (test_end_to_end_*_full_stack.py,
# inchanges par F11 : ProofPolicy.BEST_EFFORT par defaut y preserve le
# comportement exact d'avant F11), PAPER only (require_paper_mode,
# inchange).
