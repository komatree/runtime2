"""Exchange adapter baseline tests.

TODO:
- Add live-readiness blockers and retry-policy tests when implemented.
"""

from app.contracts import ExecutionIntent
from app.contracts import OrderSide
from app.contracts import OrderType
from app.contracts import TimeInForce
from app.exchanges.binance import BinanceAdapterConfig
from app.exchanges.binance import BinanceClockSync
from app.exchanges.binance import BinanceMarketDataClient
from app.exchanges.binance import BinancePublicWebSocketClient
from app.exchanges.binance import BinanceOrderClient
from app.exchanges.binance import BinanceRequestWeightTracker
from app.exchanges.binance import BinancePrivatePayloadTranslator
from app.exchanges.binance import BinancePrivateStreamClient
from app.exchanges.binance import BinancePrivateStreamState
from app.exchanges.binance import BinanceReconciliationService
from app.exchanges.binance import BinanceRecoveryAction
from app.exchanges.binance import BinanceSymbolMapping
from app.exchanges.binance import validate_endpoint_profile


def _config() -> BinanceAdapterConfig:
    return BinanceAdapterConfig(
        rest_base_url="https://api.binance.com",
        websocket_base_url="wss://stream.binance.com:9443",
        recv_window_ms=5000,
        max_clock_skew_ms=1000,
        allow_order_submission=False,
    )


def test_interface_existence() -> None:
    assert hasattr(BinanceMarketDataClient, "describe_market_data_ingestion")
    assert hasattr(BinanceMarketDataClient, "normalize_kline_stream_message")
    assert hasattr(BinancePrivateStreamClient, "describe_private_stream_requirement")
    assert hasattr(BinancePrivateStreamClient, "bootstrap_session")
    assert hasattr(BinancePrivateStreamClient, "ingest_events")
    assert hasattr(BinancePrivateStreamClient, "ingest_payloads")
    assert hasattr(BinancePrivateStreamClient, "initialize_session")
    assert hasattr(BinancePrivateStreamClient, "build_health_snapshot")
    assert hasattr(BinancePrivateStreamClient, "check_runtime_health")
    assert hasattr(BinancePrivateStreamClient, "normalize_event_payload")
    assert hasattr(BinancePrivateStreamClient, "translate_payloads")
    assert hasattr(BinancePrivatePayloadTranslator, "translate_payload")
    assert hasattr(BinancePrivatePayloadTranslator, "translate_order_execution_update")
    assert hasattr(BinancePrivatePayloadTranslator, "translate_balance_account_update")
    assert hasattr(BinancePrivatePayloadTranslator, "translate_stream_status")
    assert hasattr(BinanceOrderClient, "validate_submission_readiness")
    assert hasattr(BinanceOrderClient, "lookup_order_by_client_id")
    assert hasattr(BinanceOrderClient, "lookup_order_by_exchange_id")
    assert hasattr(BinanceOrderClient, "plan_unknown_execution_recovery")
    assert hasattr(BinanceReconciliationService, "reconcile")
    assert hasattr(BinanceReconciliationService, "lookup_stub")
    assert hasattr(BinanceReconciliationService, "build_recovery_plan")
    assert hasattr(BinanceClockSync, "check")
    assert hasattr(BinanceClockSync, "sample_server_time")
    assert hasattr(BinanceClockSync, "check_sample")
    assert hasattr(BinanceClockSync, "recalibrate")
    assert hasattr(BinanceClockSync, "recalibrate_if_needed")
    assert hasattr(BinanceClockSync, "render_operator_report")
    assert hasattr(BinanceRequestWeightTracker, "consume")
    assert callable(validate_endpoint_profile)
    assert hasattr(BinancePublicWebSocketClient, "normalize_public_message")
    assert hasattr(BinancePublicWebSocketClient, "on_disconnect")


def test_clock_sync_stub_behavior() -> None:
    sync = BinanceClockSync(_config())
    ok = sync.check(server_time_ms=1_000, local_time_ms=500)
    bad = sync.check(server_time_ms=5_000, local_time_ms=1_000)
    missing = sync.check()
    sample = sync.sample_server_time(server_time_ms=2_000, local_time_ms=1_250, round_trip_ms=40)
    sampled = sync.check_sample(sample)

    assert ok.is_within_tolerance is True
    assert ok.offset_ms == 500
    assert bad.is_within_tolerance is False
    assert bad.is_uncertain is True
    assert missing.is_within_tolerance is False
    assert missing.is_uncertain is True
    assert sampled.offset_ms == 730
    assert sampled.round_trip_ms == 40
    assert sampled.server_time_ms == 2_000


def test_reconciliation_stub_shape() -> None:
    result = BinanceReconciliationService().reconcile(
        expected_order_ids=("order-1", "order-2"),
        private_events=(private_event_with_id("unexpected-order"),),
    )

    assert result.matched_order_ids == ()
    assert result.missing_order_ids == ("order-1", "order-2")
    assert result.unknown_execution_ids == ("unexpected-order",)
    assert BinanceRecoveryAction.QUERY_ORDER_STATUS in result.recovery_actions
    assert "missing private-stream updates for one or more orders" in result.alerts
    assert "unknown execution ids observed; recovery flow required" in result.alerts


def test_client_construction() -> None:
    config = _config()
    market = BinanceMarketDataClient(
        config=config,
        symbol_mappings=(BinanceSymbolMapping(instrument_id="BTC-USDT", venue_symbol="BTCUSDT"),),
    )
    private = BinancePrivateStreamClient(config=config)
    order = BinanceOrderClient(config=config, clock_sync=BinanceClockSync(config))

    intent = ExecutionIntent(
        intent_id="intent-001",
        venue="binance",
        instrument_id="BTC-USDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.IOC,
        quantity=1,
        submitted_at=private.placeholder_event().event_time,
        source_strategy="breakout",
        rationale="test",
    )

    assert market.describe_market_data_ingestion() == "public market data ingestion placeholder"
    assert "private stream required" in private.describe_private_stream_requirement()
    assert order.validate_submission_readiness(intent) is not None


def test_private_stream_batch_and_recovery_flow_shape() -> None:
    config = _config()
    private = BinancePrivateStreamClient(config=config)
    batch = private.ingest_events(
        events=(private_event_with_id("order-1"),),
        cursor="cursor-1",
        has_gap=True,
        stream_state=BinancePrivateStreamState.STREAMING,
    )
    reconciliation = BinanceReconciliationService()
    result = reconciliation.reconcile(
        expected_order_ids=("order-1", "order-2"),
        private_events=batch.events,
    )
    plan = reconciliation.build_recovery_plan(result)

    assert batch.has_gap is True
    assert batch.cursor == "cursor-1"
    assert plan.reason == "reconciliation uncertainty"
    assert ("exchange_order_id", "order-2") in plan.order_lookup_requests
    assert BinanceRecoveryAction.HOLD_PORTFOLIO_MUTATION in plan.actions


def private_event_with_id(sequence_id: str):
    return BinancePrivateStreamClient(config=_config()).placeholder_event().__class__(
        event_type="execution_report",
        event_family=BinancePrivateStreamClient(config=_config()).placeholder_event().event_family,
        event_time=BinancePrivateStreamClient(config=_config()).placeholder_event().event_time,
        account_scope="spot",
        sequence_id=sequence_id,
        client_order_id=None,
        exchange_order_id=sequence_id,
        payload_summary={"state": "placeholder"},
    )
