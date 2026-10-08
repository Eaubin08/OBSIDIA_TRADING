"""C4.1 V0.1 interoperability evidence against the ACTUAL Trading CycleEngine.

No external broker, no real Kernel, no customer feed; controlled fake HTTP
and fake PAPER broker. Complements the historical F12 real round-trip record.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from domain.types import Mode
from execution.binder.engine import RealKernelRequiresProofRequired
from execution.binder.paper_execution import LiveModeRejected, require_paper_mode
from execution.binder.proof_policy import ProofOutcome, ProofPolicy
from governance.bridge.kx108_client import RealKX108Client, UnavailableKX108Client
from proof.receipts.receipt_store import ReceiptStore
from market.adapters.alpaca.alpaca_config import AlpacaConfig
from tests.integration.test_proof_required import UnreachableProofStore
from tests.unit.test_reference_runtime_proof_policy import _build_engine


def fake_http(body):
    def post(_url, json, timeout):  # noqa: A002
        assert json["domain"] == "trading"
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: dict(body),
        )
    return post


@pytest.mark.parametrize("branch", ["native", "external"])
def test_c41_unavailable_kernel_cannot_issue_paper_order(branch, tmp_path):
    """Same CycleEngine proof/binder semantics with optional analysis providers."""
    engine, broker = _build_engine(
        kx108_client=UnavailableKX108Client(),
        proof_policy=ProofPolicy.REQUIRED,
        proof=ReceiptStore(tmp_path / (branch + "-hold.jsonl")),
    )
    if branch == "native":
        from native.agents.adapter import NativeRosterAnalysisAdapter
        engine.analysis = NativeRosterAnalysisAdapter()
    else:
        from external.adapters.base_adapter import ExternalStackAnalysisAdapter
        from external.examples.brother_stack.example_adapter import ExampleBrotherStackAdapter
        engine.analysis = ExternalStackAnalysisAdapter(ExampleBrotherStackAdapter())
    assert engine.mode == Mode.PAPER
    outcome = engine.run_cycle()
    assert broker.submit_calls == []
    assert outcome.touched_the_market is False
    assert outcome.authority is not None
    assert outcome.authority.value in {"HOLD", "BLOCK"}
    assert outcome.proof_outcome in {ProofOutcome.PROVEN, ProofOutcome.NOT_APPLICABLE}


@pytest.mark.parametrize("response", [
    {"x108_gate": "BLOCK", "verdict": "ACT"},
    {"x108_gate": "NOPE", "verdict": "ACT"},
    {"x108_gate": None},
    {},
])
def test_c41_conflicted_kernel_transport_cannot_submit_paper(response, tmp_path):
    engine, broker = _build_engine(
        kx108_client=RealKX108Client(base_url="http://localhost:1/mock"),
        proof_policy=ProofPolicy.REQUIRED,
        proof=ReceiptStore(tmp_path / "no-order.jsonl"),
    )
    with patch("requests.post", side_effect=fake_http(response)):
        outcome = engine.run_cycle()
    assert broker.submit_calls == []
    assert not outcome.touched_the_market
    assert outcome.authority is not None
    assert outcome.authority.value != "ACT"


@pytest.mark.parametrize("gate", ["HOLD", "BLOCK"])
def test_c41_canonical_kernel_nonact_never_reaches_fake_broker(gate, tmp_path):
    engine, broker = _build_engine(
        kx108_client=RealKX108Client(base_url="http://localhost:1/mock"),
        proof_policy=ProofPolicy.REQUIRED,
        proof=ReceiptStore(tmp_path / "hold.jsonl"),
    )
    with patch("requests.post", side_effect=fake_http({"x108_gate": gate})):
        outcome = engine.run_cycle()
    assert outcome.authority is not None
    assert outcome.authority.value == gate
    assert broker.submit_calls == []
    assert not outcome.touched_the_market


def test_c41_real_kernel_constructor_requires_proof_required():
    with pytest.raises(RealKernelRequiresProofRequired):
        _build_engine(
            kx108_client=RealKX108Client(base_url="http://localhost:1/mock"),
            proof_policy=ProofPolicy.BEST_EFFORT,
        )


def test_c41_proof_unavailable_blocks_fixture_act_before_any_paper_order():
    from tests.integration.test_proof_required import _make_engine
    from tests.integration.test_paper_execution_pipeline import FakeBroker

    broker = FakeBroker()
    engine = _make_engine(
        verdict="ACT", broker=broker,
        proof=UnreachableProofStore(),
        proof_policy=ProofPolicy.REQUIRED,
    )
    outcome = engine.run_cycle()
    assert broker.submit_calls == []
    assert not outcome.touched_the_market
    assert outcome.proof_outcome is ProofOutcome.PRE_EXECUTION_PROOF_FAILURE


def test_c41_paper_mode_is_immutable_for_this_assembly():
    cfg = AlpacaConfig(
        mode=Mode.LIVE, api_key="unused-fixture", secret_key="unused-fixture",
        trading_base_url="https://api.alpaca.markets",
    )
    with pytest.raises(LiveModeRejected):
        require_paper_mode(cfg)
