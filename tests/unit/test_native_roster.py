"""Smoke test du roster natif de 17 agents (porte depuis le core actuel,
sigma/domains/trading_agents.py) et de son adapter vers le moteur de cycle."""
from __future__ import annotations

import time

from domain.market import Bar, MarketSnapshot
from domain.types import AssetClass, DataQuality, Mode, Provenance
from native.agents.adapter import ROSTER_17, NativeRosterAnalysisAdapter


def _snapshot(n_bars: int = 30) -> MarketSnapshot:
    bars = tuple(
        Bar(timestamp=float(i), open=100 + i, high=101 + i, low=99 + i, close=100.5 + i, volume=1000 + i)
        for i in range(n_bars)
    )
    return MarketSnapshot(
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        last_price=130.5,
        provenance=Provenance(source="test", fetched_at=time.time(), quality=DataQuality.LIVE, mode=Mode.SIM),
        bars=bars,
    )


def test_roster_has_exactly_17_agents() -> None:
    assert len(ROSTER_17) == 17


def test_adapter_produces_one_output_per_agent() -> None:
    adapter = NativeRosterAnalysisAdapter()
    outputs = adapter.analyse("AAPL", _snapshot(), None)
    assert len(outputs) == 17
    for output in outputs:
        assert output.signal in ("BUY", "SELL", "HOLD")
        assert 0.0 <= output.confidence <= 1.0


def test_adapter_handles_empty_history_without_crashing() -> None:
    adapter = NativeRosterAnalysisAdapter()
    outputs = adapter.analyse("AAPL", _snapshot(n_bars=0), None)
    assert len(outputs) == 17
