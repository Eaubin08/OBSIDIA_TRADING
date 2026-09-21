from __future__ import annotations

from urllib.parse import urlparse

import pytest
import requests

from domain.orders import ExecutionPlan
from domain.types import ActionKind, AssetClass, Authority, Mode, OrderStatus, OrderType, Side
from domain.ports.broker import UnauthorizedExecution
from domain.ports.market_data import MarketDataUnavailable
from market.adapters.alpaca.alpaca_broker import AlpacaBroker
from market.adapters.alpaca.alpaca_client import AlpacaHTTPClient
from market.adapters.alpaca.alpaca_config import AlpacaConfig, AlpacaConfigurationError
from market.adapters.alpaca.alpaca_market import AlpacaMarketDataProvider
from execution.binder.monitor import ExecutionMonitor
# build_alpaca_runtime (obsidia.runtime.factory) non porte a cette phase — voir le
# skip explicite plus bas et docs/MIGRATION_PROVENANCE.md pour la justification.


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeTransport:
    def __init__(self, routes=None, *, error=None):
        self.routes = dict(routes or {})
        self.error = error
        self.calls = []

    def request(self, method, url, headers=None, params=None, json=None, timeout=None):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "path": urlparse(url).path,
                "headers": dict(headers or {}),
                "params": dict(params or {}),
                "json": json,
                "timeout": timeout,
            }
        )
        if self.error is not None:
            raise self.error
        key = (method, urlparse(url).path)
        response = self.routes.get(key)
        if response is None:
            response = self.routes.get((method, "*"))
        if callable(response):
            response = response(self.calls[-1])
        return response or FakeResponse(404, {"message": f"missing route {key}"})


def _config(mode=Mode.PAPER):
    return AlpacaConfig(
        mode=mode,
        api_key="key-paper" if mode is Mode.PAPER else "key-live",
        secret_key="secret-paper" if mode is Mode.PAPER else "secret-live",
        trading_base_url=(
            "https://paper-api.alpaca.markets"
            if mode is Mode.PAPER
            else "https://api.alpaca.markets"
        ),
    )


def _client(transport, mode=Mode.PAPER):
    return AlpacaHTTPClient(_config(mode), transport=transport)


def _plan(authority=Authority.ACT, action=ActionKind.BUY, order_type=OrderType.MARKET):
    return ExecutionPlan(
        decision_id="d-test",
        symbol="AAPL",
        action=action,
        side=Side.BUY,
        quantity=2.0,
        order_type=order_type,
        authority=authority,
        limit_price=101.5 if order_type is OrderType.LIMIT else None,
    )


def _bars(count=60):
    return [
        {
            "t": f"2026-01-01T00:{i % 60:02d}:00Z",
            "o": 100 + i * 0.1,
            "h": 101 + i * 0.1,
            "l": 99 + i * 0.1,
            "c": 100.5 + i * 0.1,
            "v": 1000 + i,
        }
        for i in range(count)
    ]


def test_alpaca_config_requires_explicit_valid_mode_and_credentials(monkeypatch):
    monkeypatch.setenv("ALPACA_MODE", "paper")
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    with pytest.raises(AlpacaConfigurationError):
        AlpacaConfig.from_env()

    monkeypatch.setenv("ALPACA_MODE", "live")
    monkeypatch.setenv("ALPACA_API_KEY", "live-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "live-secret")
    cfg = AlpacaConfig.from_env()
    assert cfg.mode is Mode.LIVE
    assert cfg.trading_base_url == "https://api.alpaca.markets"

    monkeypatch.setenv("ALPACA_MODE", "demo")
    with pytest.raises(AlpacaConfigurationError):
        AlpacaConfig.from_env()


def test_alpaca_market_maps_trade_quote_and_bars_without_sdk_types():
    transport = FakeTransport(
        {
            ("GET", "/v2/stocks/AAPL/trades/latest"): FakeResponse(
                payload={"trade": {"p": "123.45", "t": "2026-01-01T12:00:00Z"}}
            ),
            ("GET", "/v2/stocks/AAPL/quotes/latest"): FakeResponse(
                payload={
                    "quote": {
                        "bp": "123.40",
                        "ap": "123.50",
                        "bs": "10",
                        "as": "15",
                        "t": "2026-01-01T12:00:01Z",
                    }
                }
            ),
            ("GET", "/v2/stocks/AAPL/bars"): FakeResponse(payload={"bars": _bars(2)}),
        }
    )
    market = AlpacaMarketDataProvider(_client(transport))

    snapshot = market.snapshot("AAPL")

    assert snapshot.symbol == "AAPL"
    assert snapshot.asset_class is AssetClass.EQUITY
    assert snapshot.last_price == 123.45
    assert snapshot.quote is not None
    assert snapshot.quote.spread_bps is not None
    assert snapshot.provenance.source == "alpaca"
    assert snapshot.provenance.mode is Mode.PAPER


def test_alpaca_market_missing_price_is_explicit_error():
    transport = FakeTransport(
        {
            ("GET", "/v2/stocks/AAPL/trades/latest"): FakeResponse(payload={"trade": {}}),
            ("GET", "/v2/stocks/AAPL/quotes/latest"): FakeResponse(payload={"quote": {}}),
            ("GET", "/v2/stocks/AAPL/bars"): FakeResponse(payload={"bars": []}),
        }
    )
    market = AlpacaMarketDataProvider(_client(transport))

    with pytest.raises(MarketDataUnavailable):
        market.snapshot("AAPL")


def test_alpaca_market_timeout_is_degraded_as_unavailable():
    market = AlpacaMarketDataProvider(_client(FakeTransport(error=requests.Timeout())))

    with pytest.raises(MarketDataUnavailable):
        market.snapshot("AAPL")


def test_alpaca_broker_maps_account_positions_orders_and_portfolio():
    transport = FakeTransport(
        {
            ("GET", "/v2/account"): FakeResponse(
                payload={
                    "id": "acct-1",
                    "equity": "10000",
                    "cash": "4000",
                    "buying_power": "8000",
                    "last_equity": "9900",
                    "currency": "USD",
                }
            ),
            ("GET", "/v2/positions"): FakeResponse(
                payload=[
                    {
                        "symbol": "AAPL",
                        "asset_class": "us_equity",
                        "qty": "3",
                        "avg_entry_price": "120",
                        "current_price": "125",
                        "market_value": "375",
                        "unrealized_pl": "15",
                    }
                ]
            ),
            ("GET", "/v2/orders"): FakeResponse(
                payload=[
                    {
                        "id": "ord-1",
                        "symbol": "AAPL",
                        "side": "buy",
                        "qty": "3",
                        "type": "limit",
                        "status": "partially_filled",
                        "filled_qty": "1",
                        "filled_avg_price": "124",
                        "limit_price": "125",
                        "time_in_force": "day",
                    }
                ]
            ),
        }
    )
    broker = AlpacaBroker(_client(transport))

    portfolio = broker.portfolio()

    assert portfolio.account.equity == 10000
    assert portfolio.positions[0].quantity == 3
    assert portfolio.positions[0].unrealized_pnl == 15
    assert portfolio.open_orders[0].status is OrderStatus.PARTIALLY_FILLED
    assert portfolio.open_orders[0].remaining_quantity == 2


def test_alpaca_broker_refuses_hold_block_and_wait_before_submit():
    transport = FakeTransport()
    broker = AlpacaBroker(_client(transport))

    for plan in (
        _plan(authority=Authority.HOLD),
        _plan(authority=Authority.BLOCK),
        _plan(authority=Authority.ACT, action=ActionKind.WAIT),
    ):
        with pytest.raises(UnauthorizedExecution):
            broker.submit(plan)

    assert not [c for c in transport.calls if c["method"] == "POST"]


def test_alpaca_broker_submits_market_and_limit_only_after_act():
    def create_order(call):
        return FakeResponse(
            payload={
                "id": "ord-act",
                "symbol": call["json"]["symbol"],
                "status": "new",
                "submitted_at": "2026-01-01T12:00:00Z",
                "filled_qty": "0",
            }
        )

    transport = FakeTransport({("POST", "/v2/orders"): create_order})
    broker = AlpacaBroker(_client(transport))

    result = broker.submit(_plan(order_type=OrderType.LIMIT))

    assert result.submitted is True
    assert result.status is OrderStatus.ACCEPTED
    assert result.broker_order_id == "ord-act"
    assert transport.calls[-1]["json"]["type"] == "limit"
    assert transport.calls[-1]["json"]["limit_price"] == "101.5"


def test_alpaca_broker_execution_result_keeps_pass7_lifecycle_provenance():
    transport = FakeTransport(
        {
            ("POST", "/v2/orders"): FakeResponse(
                payload={
                    "id": "ord-filled",
                    "symbol": "AAPL",
                    "status": "filled",
                    "submitted_at": "2026-01-01T12:00:00Z",
                    "updated_at": "2026-01-01T12:00:02Z",
                    "filled_at": "2026-01-01T12:00:03Z",
                    "filled_qty": "2",
                    "filled_avg_price": "101.25",
                }
            )
        }
    )
    broker = AlpacaBroker(_client(transport))

    result = broker.submit(_plan())
    payload = result.as_dict()

    assert result.status is OrderStatus.FILLED
    assert result.lifecycle_status == "FILLED"
    assert result.provider == "alpaca"
    assert result.mode == Mode.PAPER.value
    assert result.updated_at is not None
    assert result.filled_at is not None
    assert payload["execution_plan_id"] == result.plan.causal_id
    assert payload["provenance"]["source"] == "alpaca"
    assert result.fills[0].quantity == 2
    assert result.fills[0].price == 101.25


def test_alpaca_broker_rejected_order_is_explicit_not_fake_fill():
    transport = FakeTransport(
        {
            ("POST", "/v2/orders"): FakeResponse(
                422, {"message": "insufficient buying power"}
            )
        }
    )
    broker = AlpacaBroker(_client(transport))

    result = broker.submit(_plan())

    assert result.submitted is False
    assert result.status is OrderStatus.REJECTED
    assert result.fills == ()
    assert "insufficient buying power" in result.rejected_reason


def test_execution_monitor_observes_partial_fill_from_alpaca_order_status():
    transport = FakeTransport(
        {
            ("GET", "/v2/orders/ord-1"): FakeResponse(
                payload={
                    "id": "ord-1",
                    "symbol": "AAPL",
                    "side": "buy",
                    "qty": "10",
                    "type": "market",
                    "status": "partially_filled",
                    "filled_qty": "4",
                    "filled_avg_price": "101",
                    "time_in_force": "day",
                }
            ),
            ("GET", "/v2/account"): FakeResponse(
                payload={"equity": "10000", "cash": "9000", "buying_power": "9000"}
            ),
            ("GET", "/v2/positions"): FakeResponse(payload=[]),
            ("GET", "/v2/orders"): FakeResponse(payload=[]),
        }
    )
    broker = AlpacaBroker(_client(transport))
    monitor = ExecutionMonitor(broker)
    execution = broker._execution_from(
        _plan(),
        {"id": "ord-1", "status": "new", "submitted_at": "2026-01-01T12:00:00Z"},
        submitted=True,
    )
    monitor.track(execution)

    report = monitor.poll()

    assert report.orders[0].current_status is OrderStatus.PARTIALLY_FILLED
    assert report.orders[0].filled_quantity == 4
    assert report.orders[0].changed is True


def test_no_secret_leakage_in_client_errors():
    transport = FakeTransport({("GET", "/v2/account"): FakeResponse(403, {"message": "forbidden"})})
    client = _client(transport)
    broker = AlpacaBroker(client)

    with pytest.raises(Exception) as exc:
        broker.account()

    assert "secret" not in str(exc.value)
    assert "key-paper" not in str(exc.value)


def test_provider_isolation_from_domain_core_and_agents():
    # Chemins adaptes a la structure OBSIDIA_TRADING (F2/F3, 2026-09-21) :
    # domain/ et native/agents/ ne doivent jamais dependre d'un provider Alpaca.
    forbidden_roots = ["domain", "native/agents"]
    for root in forbidden_roots:
        for path in __import__("pathlib").Path(root).rglob("*.py"):
            content = path.read_text(encoding="utf-8")
            assert "market.adapters.alpaca" not in content
            assert "alpaca_trade_api" not in content


@pytest.mark.skip(
    reason=(
        "build_alpaca_runtime vit dans obsidia/runtime/factory.py (agent-trad-main), "
        "qui depend du sous-systeme obsidia/adapters/* (legacy_agents, legacy_guard, "
        "legacy_market, legacy_proof, legacy_strategy, jsonl_memory, jsonl_order_ledger, "
        "sim_broker) — hors perimetre F2/F3 (Market+Domain/Agents). Ce wiring complet "
        "releve de F6 Execution (Binder + factory). Voir docs/MIGRATION_PROVENANCE.md."
    )
)
def test_build_alpaca_runtime_uses_same_engine_without_credentials():
    transport = FakeTransport(
        {
            ("GET", "/v2/stocks/AAPL/trades/latest"): FakeResponse(
                payload={"trade": {"p": "106.5", "t": "2026-01-01T12:00:00Z"}}
            ),
            ("GET", "/v2/stocks/AAPL/quotes/latest"): FakeResponse(
                payload={"quote": {"bp": "106.4", "ap": "106.6"}}
            ),
            ("GET", "/v2/stocks/AAPL/bars"): FakeResponse(payload={"bars": _bars(80)}),
            ("GET", "/v2/account"): FakeResponse(
                payload={"equity": "10000", "cash": "10000", "buying_power": "10000"}
            ),
            ("GET", "/v2/positions"): FakeResponse(payload=[]),
            ("GET", "/v2/orders"): FakeResponse(payload=[]),
            ("GET", "/v1beta1/news"): FakeResponse(payload={"news": []}),
        }
    )

    handles = build_alpaca_runtime(
        symbol="AAPL",
        config=_config(Mode.PAPER),
        transport=transport,
        persist_proofs=False,
    )
    snapshot = handles.bus.step()

    assert handles.mode is Mode.PAPER
    assert snapshot.cycle_count == 1
    assert snapshot.last_cycle["state"]["mode"] == "PAPER"
    assert snapshot.last_cycle["touched_the_market"] is False
