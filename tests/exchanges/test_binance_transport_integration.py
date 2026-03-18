"""Binance transport-backed private stream and status lookup tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from urllib.parse import parse_qs
from urllib.parse import urlparse

from app.contracts import OrderStatus
from app.contracts import OrderSide
from app.contracts import OrderType
from app.contracts import ReconciliationState
from app.exchanges.binance import BinanceAdapterConfig
from app.exchanges.binance import BinanceOrderClient
from app.exchanges.binance import BinancePrivatePayloadTranslator
from app.exchanges.binance import BinancePrivateStreamClient
from app.exchanges.binance import BinanceRequestWeightTracker
from app.exchanges.binance import BinancePrivateUserDataTransport
from app.exchanges.binance import BinanceSignedRestAccountSnapshotBootstrap
from app.exchanges.binance import BinanceSignedRestOrderStatusTransport
from app.exchanges.binance import BinanceSymbolMapping
from app.exchanges.binance import BinanceReconciliationService


def test_transport_backed_private_event_ingestion_shape() -> None:
    websocket_factory = _FakeWebSocketFactory(
        messages=(
            json.dumps({"id": 1, "status": 200, "result": {"subscriptionId": 7}}),
            json.dumps(_execution_report_payload(order_id=1001, status="FILLED", execution_type="TRADE")),
        )
    )
    transport = BinancePrivateUserDataTransport(
        rest_base_url="https://api.binance.com",
        websocket_base_url="wss://stream.binance.com:9443",
        api_key="key",
        api_secret="secret",
        websocket_factory=websocket_factory,
        request_weight_tracker=BinanceRequestWeightTracker(max_weight=10),
    )
    client = _private_client()
    translator = _translator()

    session = client.bootstrap_session(transport=transport, started_at=_ts())
    payload = transport.read_payload(connection_id=session.connection_id or "")
    batch = client.ingest_payloads(payloads=(payload,))
    translations = client.translate_payloads(payloads=(payload,), translator=translator)

    assert session.connection_id == "private-connection-1"
    assert session.subscription_id == "7"
    assert batch.last_sequence_id == "1001"
    assert translations[0].order_state is not None
    assert translations[0].fill_event is not None
    assert transport.latest_weight_snapshot() is not None
    assert transport.latest_weight_snapshot().used_weight == 2


def test_signed_status_query_lookup_path() -> None:
    urlopen = _FakeUrlOpen(
        responses=[
            _response(
                {
                    "symbol": "BTCUSDT",
                    "status": "FILLED",
                    "side": "BUY",
                    "type": "MARKET",
                    "origQty": "0.01",
                    "executedQty": "0.01",
                    "cummulativeQuoteQty": "359.069",
                    "price": "0",
                    "updateTime": 1773360001000,
                    "orderId": 1002,
                    "origClientOrderId": "client-1002",
                },
                headers={"X-MBX-USED-WEIGHT-1M": "8"},
            )
        ]
    )
    transport = BinanceSignedRestOrderStatusTransport(
        config=_config(),
        venue_symbol="BTCUSDT",
        time_provider=lambda: 1773360000000,
        urlopen_fn=urlopen,
        request_weight_tracker=BinanceRequestWeightTracker(max_weight=20),
    )
    client = BinanceOrderClient(config=_config(), clock_sync=_clock_sync())

    result = client.lookup_order_by_exchange_id("1002", transport=transport)
    health = transport.last_health()

    assert result.found is True
    assert result.status_summary == "filled"
    assert result.source == "signed_rest_order_lookup"
    assert result.recovered_order_state is not None
    assert result.recovered_order_state.status is OrderStatus.FILLED
    assert result.recovered_order_state.filled_quantity == Decimal("0.01")
    assert result.recovered_fill_events[0].order_id == "1002"
    assert result.recovered_fill_events[0].quantity == Decimal("0.01")
    assert result.recovered_fill_events[0].price == Decimal("35906.9")
    assert health is not None
    assert health.state.value == "success"
    assert health.request_weight_used == 8
    assert health.endpoint_profile_name == "binance_spot_prod"
    assert "signature=" in urlopen.calls[0]["url"]
    assert urlopen.calls[0]["headers"]["X-mbx-apikey"] == "key"


def test_signed_account_snapshot_bootstrap_path() -> None:
    urlopen = _FakeUrlOpen(
        responses=[
            _response(
                {
                    "updateTime": 1773360001000,
                    "balances": [
                        {"asset": "BTC", "free": "1.25", "locked": "0.00"},
                        {"asset": "USDT", "free": "900.0", "locked": "25.0"},
                        {"asset": "ETH", "free": "0", "locked": "0"},
                    ],
                }
            )
        ]
    )
    bootstrap = BinanceSignedRestAccountSnapshotBootstrap(
        config=_config(),
        time_provider=lambda: 1773360000000,
        urlopen_fn=urlopen,
    )

    snapshot = bootstrap.fetch_snapshot()

    assert snapshot.source_event_type == "restAccountSnapshot"
    assert tuple(balance.asset for balance in snapshot.balances) == ("BTC", "USDT")
    assert "signature=" in urlopen.calls[0]["url"]
    assert urlopen.calls[0]["headers"]["X-mbx-apikey"] == "key"


def test_reconciliation_is_driven_by_transport_interfaces() -> None:
    urlopen = _FakeUrlOpen(
        responses=[
            _response({
                "symbol": "BTCUSDT",
                "status": "FILLED",
                "side": "BUY",
                "type": "MARKET",
                "origQty": "0.01",
                "executedQty": "0.01",
                "cummulativeQuoteQty": "358.500",
                "price": "0",
                "updateTime": 1773360001000,
                "orderId": 2002,
                "origClientOrderId": "client-2002",
            }),
        ]
    )
    websocket_factory = _FakeWebSocketFactory(
        messages=(
            json.dumps({"id": 1, "status": 200, "result": {"subscriptionId": 8}}),
            json.dumps(_terminated_payload()),
        )
    )
    private_transport = BinancePrivateUserDataTransport(
        rest_base_url="https://api.binance.com",
        websocket_base_url="wss://stream.binance.com:9443",
        api_key="key",
        api_secret="secret",
        websocket_factory=websocket_factory,
        urlopen_fn=urlopen,
    )
    status_transport = BinanceSignedRestOrderStatusTransport(
        config=_config(),
        venue_symbol="BTCUSDT",
        time_provider=lambda: 1773360000000,
        urlopen_fn=urlopen,
    )
    private_client = _private_client()
    session = private_client.bootstrap_session(transport=private_transport, started_at=_ts())

    result = BinanceReconciliationService().reconcile_with_transports(
        expected_order_ids=("2002",),
        private_payloads=(private_transport.read_payload(connection_id=session.connection_id or ""),),
        private_stream_client=private_client,
        translator=_translator(),
        order_client=BinanceOrderClient(config=_config(), clock_sync=_clock_sync()),
        lookup_transport=status_transport,
        session=session,
        occurred_at=_ts(),
    )

    recovered = [state for state in result.workflow_result.order_states if state.order_id == "2002"][-1]

    assert result.batch_health is not None
    assert result.batch_health.state.value == "terminated"
    assert result.translations[0].stream_invalidated is True
    assert result.reconciliation_result.missing_order_ids == ("2002",)
    assert recovered.reconciliation_state is ReconciliationState.RECOVERED_TERMINAL_STATE
    assert result.workflow_result.recovered_fill_events[0].order_id == "2002"
    assert result.status_query_health[-1].state.value == "success"


def test_signed_status_query_throttles_when_request_weight_budget_exceeded() -> None:
    transport = BinanceSignedRestOrderStatusTransport(
        config=_config(),
        venue_symbol="BTCUSDT",
        time_provider=lambda: 1773360000000,
        urlopen_fn=_FakeUrlOpen(responses=[]),
        request_weight_tracker=BinanceRequestWeightTracker(max_weight=2),
        request_weight_cost=4,
    )

    result = transport.lookup_by_exchange_order_id(exchange_order_id="1003")
    health = transport.last_health()

    assert result.found is False
    assert "request-weight budget exceeded" in (result.alert or "")
    assert health is not None
    assert health.state.value == "blocked"
    assert health.request_weight_limit == 2


def test_private_transport_rejects_endpoint_profile_mismatch() -> None:
    try:
        BinancePrivateUserDataTransport(
            rest_base_url="https://testnet.binance.vision",
            websocket_base_url="wss://stream.binance.com:9443",
            api_key="key",
            api_secret="secret",
            endpoint_profile_name="binance_spot_prod",
        )
    except ValueError as exc:
        assert "does not match endpoint profile" in str(exc)
    else:
        raise AssertionError("expected endpoint profile mismatch to fail closed")


def test_private_transport_unwraps_data_wrapper_payload() -> None:
    transport = BinancePrivateUserDataTransport(
        rest_base_url="https://api.binance.com",
        websocket_base_url="wss://stream.binance.com:9443",
        api_key="key",
        api_secret="secret",
        websocket_factory=_FakeWebSocketFactory(
            messages=(
                json.dumps({"id": 1, "status": 200, "result": {"subscriptionId": 9}}),
                json.dumps({"subscriptionId": "9", "event": _execution_report_payload(order_id=3001, status="FILLED", execution_type="TRADE")}),
            )
        ),
    )
    session = _private_client().bootstrap_session(transport=transport, started_at=_ts())

    payload = transport.read_payload(connection_id=session.connection_id or "")

    assert payload["e"] == "executionReport"
    assert payload["i"] == 3001


@dataclass
class _FakeWebSocketConnection:
    messages: list[str]
    closed: bool = False

    def recv_text(self) -> str:
        return self.messages.pop(0)

    def send_text(self, text: str) -> None:
        return None

    def close(self) -> None:
        self.closed = True


@dataclass
class _FakeWebSocketFactory:
    messages: tuple[str, ...]

    def connect(self, *, url: str, headers: dict[str, str] | None = None):
        return _FakeWebSocketConnection(messages=list(self.messages))


class _FakeHttpResponse:
    def __init__(
        self,
        payload: object,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._payload = payload
        self.status = status
        self.headers = headers or {}

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


@dataclass
class _FakeUrlOpen:
    responses: list[tuple[object, int, dict[str, str]]]

    def __post_init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, request):
        self.calls.append(
            {
                "url": request.full_url,
                "method": request.get_method(),
                "headers": dict(request.header_items()),
                "query": parse_qs(urlparse(request.full_url).query),
            }
        )
        payload, status, headers = self.responses.pop(0)
        return _FakeHttpResponse(payload, status=status, headers=headers)


def _response(
    payload: object,
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> tuple[object, int, dict[str, str]]:
    return (payload, status, headers or {})


def _config() -> BinanceAdapterConfig:
    return BinanceAdapterConfig(
        rest_base_url="https://api.binance.com",
        websocket_base_url="wss://stream.binance.com:9443",
        api_key="key",
        api_secret="secret",
    )


def _private_client() -> BinancePrivateStreamClient:
    return BinancePrivateStreamClient(config=_config())


def _translator() -> BinancePrivatePayloadTranslator:
    return BinancePrivatePayloadTranslator(
        symbol_mappings=(BinanceSymbolMapping(instrument_id="BTC-USDT", venue_symbol="BTCUSDT"),),
    )


def _clock_sync():
    from app.exchanges.binance import BinanceClockSync

    return BinanceClockSync(_config())


def _execution_report_payload(*, order_id: int, status: str, execution_type: str) -> dict[str, object]:
    return {
        "e": "executionReport",
        "E": 1773360000000,
        "s": "BTCUSDT",
        "c": f"client-{order_id}",
        "S": "BUY",
        "o": "MARKET",
        "X": status,
        "x": execution_type,
        "q": "1",
        "z": "1",
        "l": "1",
        "L": "100000",
        "Z": "100000",
        "n": "1",
        "N": "USDT",
        "i": order_id,
        "t": order_id + 5000,
        "m": False,
    }


def _terminated_payload() -> dict[str, object]:
    return {
        "e": "listenKeyExpired",
        "E": 1773360000000,
    }


def _ts() -> datetime:
    return datetime(2026, 3, 13, 0, 0, tzinfo=UTC)
