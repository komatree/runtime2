"""Binance reconciliation workflow tests.

TODO:
- Add richer replay/cursor tests once operational thresholds are finalized.
"""

from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.contracts import FillEvent
from app.contracts import LiquidityRole
from app.contracts import OrderSide
from app.contracts import OrderState
from app.contracts import OrderType
from app.exchanges.binance import BinanceAdapterConfig
from app.exchanges.binance import BinanceOrderClient
from app.contracts import OrderStatus
from app.contracts import ReconciliationState
from app.exchanges.binance import BinanceOrderLookupResult
from app.exchanges.binance import BinanceOrderReconciliationResult
from app.exchanges.binance import BinanceReconciliationCoordinator
from app.exchanges.binance import BinanceReconciliationService
from app.exchanges.binance import BinancePrivatePayloadTranslator
from app.exchanges.binance import BinancePrivateStreamClient
from app.exchanges.binance import BinanceSignedRestOrderStatusTransport
from app.exchanges.binance import BinanceSymbolMapping
from app.storage import JsonBinanceReconciliationStateStore
from app.storage import JsonlReconciliationPersistenceGateway


def test_unknown_execution_transition() -> None:
    workflow = BinanceReconciliationCoordinator().coordinate(
        reconciliation_result=BinanceOrderReconciliationResult(
            matched_order_ids=(),
            missing_order_ids=("order-1",),
            unknown_execution_ids=("ghost-order",),
            alerts=("gap detected",),
        ),
        occurred_at=_ts(),
    )

    states = {event.order_id: event.reconciliation_state for event in workflow.reconciliation_events}

    assert states["ghost-order"] is ReconciliationState.UNKNOWN_EXECUTION
    assert states["order-1"] is ReconciliationState.STATUS_QUERY_PENDING
    assert "gap detected" in workflow.alerts


def test_successful_status_recovery() -> None:
    workflow = BinanceReconciliationCoordinator().coordinate(
        reconciliation_result=BinanceOrderReconciliationResult(
            matched_order_ids=("order-1",),
            missing_order_ids=("order-2",),
            unknown_execution_ids=(),
            alerts=(),
        ),
        lookup_results=(
            BinanceOrderLookupResult(
                found=False,
                lookup_field="exchange_order_id",
                lookup_value="order-2",
                source="rest_status",
                status_summary=None,
                alert="not yet visible",
                attempt_number=1,
            ),
            BinanceOrderLookupResult(
                found=True,
                lookup_field="exchange_order_id",
                lookup_value="order-2",
                source="rest_status",
                status_summary="filled",
                recovered_order_state=OrderState(
                    venue="binance",
                    order_id="order-2",
                    client_order_id="client-2",
                    instrument_id="BTC-USDT",
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    status=OrderStatus.FILLED,
                    requested_quantity=Decimal("1"),
                    filled_quantity=Decimal("1"),
                    remaining_quantity=Decimal("0"),
                    last_update_time=_ts(),
                    average_fill_price=Decimal("100"),
                ),
                recovered_fill_events=(
                    FillEvent(
                        venue="binance",
                        order_id="order-2",
                        fill_id="order-2:recovered",
                        instrument_id="BTC-USDT",
                        side=OrderSide.BUY,
                        quantity=Decimal("1"),
                        price=Decimal("100"),
                        fee=Decimal("0"),
                        fee_asset="USDT",
                        occurred_at=_ts(),
                        liquidity_role=LiquidityRole.UNKNOWN,
                    ),
                ),
                attempt_number=2,
            ),
        ),
        occurred_at=_ts(),
    )

    matched_state = [state for state in workflow.order_states if state.order_id == "order-1"][-1]
    recovered_state = [state for state in workflow.order_states if state.order_id == "order-2"][-1]
    recovery_summary = workflow.recovery_summaries[0]

    assert matched_state.reconciliation_state is ReconciliationState.SUBMIT_SENT
    assert recovered_state.reconciliation_state is ReconciliationState.RECOVERED_TERMINAL_STATE
    assert recovered_state.status is OrderStatus.FILLED
    assert recovered_state.filled_quantity == Decimal("1")
    assert recovery_summary.attempts == 2
    assert recovery_summary.terminal_status == "filled"
    assert workflow.recovered_fill_events[0].fill_id == "order-2:recovered"


def test_unresolved_recovery_path_persists_append_only(tmp_path: Path) -> None:
    workflow = BinanceReconciliationCoordinator(max_recovery_attempts=3).coordinate(
        reconciliation_result=BinanceOrderReconciliationResult(
            matched_order_ids=(),
            missing_order_ids=("order-3",),
            unknown_execution_ids=(),
            alerts=("missing update",),
        ),
        lookup_results=(
            BinanceOrderLookupResult(
                found=False,
                lookup_field="client_order_id",
                lookup_value="client-3",
                source="rest_status",
                status_summary=None,
                alert="status lookup unresolved",
                attempt_number=1,
            ),
            BinanceOrderLookupResult(
                found=False,
                lookup_field="client_order_id",
                lookup_value="client-3",
                source="rest_status",
                status_summary=None,
                alert="status lookup unresolved",
                attempt_number=2,
            ),
            BinanceOrderLookupResult(
                found=False,
                lookup_field="client_order_id",
                lookup_value="client-3",
                source="rest_status",
                status_summary=None,
                alert="status lookup unresolved",
                attempt_number=3,
            ),
        ),
        occurred_at=_ts(),
    )

    unresolved = [state for state in workflow.order_states if state.order_id == "client-3"][-1]
    assert unresolved.status is OrderStatus.UNRECONCILED
    assert unresolved.reconciliation_state is ReconciliationState.UNRECONCILED_MANUAL_ATTENTION
    assert "manual attention required" in workflow.alerts[-1]
    assert workflow.recovery_summaries[0].attempts == 3

    output_path = tmp_path / "reconciliation.jsonl"
    gateway = JsonlReconciliationPersistenceGateway(output_path=output_path)
    gateway.persist_workflow(workflow)
    gateway.persist_workflow(workflow)

    lines = output_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    payload = json.loads(lines[0])
    assert payload["schema_version"] == "binance_reconciliation_workflow.v3"
    assert payload["recovery_attempt_count"] == 3
    assert payload["workflow"]["convergence_state"] == "unreconciled_manual_attention"
    assert payload["workflow"]["recovery_attempts"][0]["lookup_field"] == "client_order_id"
    assert (
        payload["workflow"]["reconciliation_events"][-1]["reconciliation_state"]
        == "unreconciled_manual_attention"
    )


def test_pending_recovery_stays_inspectable_until_convergence_or_escalation() -> None:
    workflow = BinanceReconciliationCoordinator(max_recovery_attempts=3).coordinate(
        reconciliation_result=BinanceOrderReconciliationResult(
            matched_order_ids=(),
            missing_order_ids=("order-4",),
            unknown_execution_ids=(),
            alerts=(),
        ),
        lookup_results=(
            BinanceOrderLookupResult(
                found=True,
                lookup_field="exchange_order_id",
                lookup_value="order-4",
                source="rest_status",
                status_summary="acknowledged",
                attempt_number=1,
            ),
            BinanceOrderLookupResult(
                found=True,
                lookup_field="exchange_order_id",
                lookup_value="order-4",
                source="rest_status",
                status_summary="partially_filled",
                attempt_number=2,
            ),
        ),
        occurred_at=_ts(),
    )

    pending_state = [state for state in workflow.order_states if state.order_id == "order-4"][-1]

    assert pending_state.reconciliation_state is ReconciliationState.STATUS_QUERY_PENDING
    assert pending_state.status is OrderStatus.RECOVERING
    assert workflow.recovery_summaries[0].attempts == 2
    assert workflow.recovery_summaries[0].terminal_status is None


def test_duplicate_recovery_attempt_handling_is_replay_safe(tmp_path: Path) -> None:
    store = JsonBinanceReconciliationStateStore(state_path=tmp_path / "reconciliation_state.json")
    lookup = BinanceOrderLookupResult(
        found=False,
        lookup_field="exchange_order_id",
        lookup_value="order-5",
        source="signed_rest_order_lookup",
        status_summary=None,
        alert="not yet visible",
    )

    first = store.register_lookup_results(
        lookup_results=(lookup,),
        occurred_at=_ts(),
        cursor_token="cursor-1",
    )
    second = store.register_lookup_results(
        lookup_results=(lookup,),
        occurred_at=_ts(),
        cursor_token="cursor-1",
    )
    snapshot = store.load_snapshot()

    assert first[0].attempt_number == 1
    assert second[0].attempt_number == 1
    assert len(snapshot.persisted_attempts) == 1


def test_restart_recovery_reloads_unresolved_state_and_resumes_safely(tmp_path: Path) -> None:
    store = JsonBinanceReconciliationStateStore(state_path=tmp_path / "reconciliation_state.json")
    client = BinancePrivateStreamClient(config=_config())
    service = BinanceReconciliationService()
    order_client = BinanceOrderClient(config=_config(), clock_sync=_clock_sync())
    lookup_transport = BinanceSignedRestOrderStatusTransport(
        config=_config(),
        venue_symbol="BTCUSDT",
        time_provider=lambda: 1773360000000,
        urlopen_fn=_FakeUrlOpen(
            responses=[
                {
                    "symbol": "BTCUSDT",
                    "status": "FILLED",
                    "orderId": 6001,
                    "origClientOrderId": "client-6001",
                }
            ]
        ),
    )

    first_result = service.reconcile_with_transports(
        expected_order_ids=("6001",),
        private_payloads=(),
        private_stream_client=client,
        translator=_translator(),
        order_client=order_client,
        lookup_transport=lookup_transport,
        state_store=store,
        cursor="restart-1",
        occurred_at=_ts(),
    )
    first_snapshot = store.load_snapshot()

    assert "6001" not in first_snapshot.unresolved_order_ids
    assert first_result.workflow_result.recovery_summaries[0].attempts == 1
    assert first_result.workflow_result.recovery_trigger_reason == "missing_private_updates"
    assert first_result.workflow_result.recovery_automatic is True

    unresolved_workflow = BinanceReconciliationCoordinator(max_recovery_attempts=3).coordinate(
        reconciliation_result=BinanceOrderReconciliationResult(
            matched_order_ids=(),
            missing_order_ids=("7001",),
            unknown_execution_ids=(),
            alerts=("missing update",),
        ),
        occurred_at=_ts(),
    )
    store.persist_workflow_state(
        workflow=unresolved_workflow,
        occurred_at=_ts(),
        cursor_token="restart-pending",
        has_gap=False,
    )

    resumed_lookup_transport = BinanceSignedRestOrderStatusTransport(
        config=_config(),
        venue_symbol="BTCUSDT",
        time_provider=lambda: 1773360000000,
        urlopen_fn=_FakeUrlOpen(
            responses=[
                {
                    "symbol": "BTCUSDT",
                    "status": "FILLED",
                    "orderId": 7001,
                    "origClientOrderId": "client-7001",
                }
            ]
        ),
    )

    resumed_result = service.reconcile_with_transports(
        expected_order_ids=(),
        private_payloads=(),
        private_stream_client=client,
        translator=_translator(),
        order_client=order_client,
        lookup_transport=resumed_lookup_transport,
        state_store=store,
        cursor="restart-2",
        occurred_at=_ts(),
    )
    resumed_snapshot = store.load_snapshot()

    recovered = [state for state in resumed_result.workflow_result.order_states if state.order_id == "7001"][-1]
    assert recovered.reconciliation_state is ReconciliationState.RECOVERED_TERMINAL_STATE
    assert "7001" not in resumed_snapshot.unresolved_order_ids
    assert resumed_result.workflow_result.recovery_trigger_reason == "restart_resume"
    assert resumed_result.workflow_result.resumed_from_snapshot is True
    assert resumed_snapshot.last_recovery_trigger_reason == "restart_resume"
    assert resumed_snapshot.last_convergence_state == "converged_terminal"


def test_gap_recovery_persistence_records_cursor_and_unresolved_state(tmp_path: Path) -> None:
    store = JsonBinanceReconciliationStateStore(state_path=tmp_path / "reconciliation_state.json")
    result = BinanceReconciliationService().reconcile_with_transports(
        expected_order_ids=("8001",),
        private_payloads=(),
        private_stream_client=BinancePrivateStreamClient(config=_config()),
        translator=_translator(),
        order_client=BinanceOrderClient(config=_config(), clock_sync=_clock_sync()),
            lookup_transport=BinanceSignedRestOrderStatusTransport(
                config=_config(),
                venue_symbol="BTCUSDT",
                time_provider=lambda: 1773360000000,
                urlopen_fn=_FakeUrlOpen(
                    responses=[
                        {
                            "symbol": "BTCUSDT",
                            "status": "NEW",
                            "orderId": 8001,
                            "origClientOrderId": "client-8001",
                        },
                        {
                            "symbol": "BTCUSDT",
                            "status": "NEW",
                            "orderId": 8001,
                            "origClientOrderId": "client-8001",
                        },
                        {
                            "symbol": "BTCUSDT",
                            "status": "NEW",
                            "orderId": 8001,
                            "origClientOrderId": "client-8001",
                        },
                    ]
                ),
            ),
        state_store=store,
        cursor="gap-8001",
        has_gap=True,
        occurred_at=_ts(),
    )

    snapshot = store.load_snapshot()

    assert result.cursor_snapshot is not None
    assert result.cursor_snapshot.private_stream_cursor == "gap-8001"
    assert snapshot.gap_active is True
    assert result.workflow_result.recovery_trigger_reason == "private_stream_gap"
    assert result.workflow_result.gap_detected is True
    assert snapshot.last_recovery_trigger_reason == "private_stream_gap"
    assert snapshot.last_convergence_state == "pending"


def test_gap_detected_triggers_automatic_status_query_recovery() -> None:
    service = BinanceReconciliationService()
    plan = service.build_automatic_recovery_plan(
        result=BinanceOrderReconciliationResult(
            matched_order_ids=(),
            missing_order_ids=("gap-order",),
            unknown_execution_ids=(),
            alerts=("gap detected",),
            recovery_actions=(),
        ),
        gap_detected=True,
        resumed_from_snapshot=False,
    )

    assert plan.automatic_triggered is True
    assert plan.trigger_reason.value == "private_stream_gap"
    assert plan.order_lookup_requests == (("exchange_order_id", "gap-order"),)
    assert "automatic recovery triggered by private-stream gap" in plan.alerts


def test_gap_recovery_remains_unresolved_and_escalates_with_restart_safe_state(tmp_path: Path) -> None:
    store = JsonBinanceReconciliationStateStore(state_path=tmp_path / "reconciliation_state.json")
    result = BinanceReconciliationService().reconcile_with_transports(
        expected_order_ids=("escalate-1",),
        private_payloads=(),
        private_stream_client=BinancePrivateStreamClient(config=_config()),
        translator=_translator(),
        order_client=BinanceOrderClient(config=_config(), clock_sync=_clock_sync()),
        lookup_transport=BinanceSignedRestOrderStatusTransport(
            config=_config(),
            venue_symbol="BTCUSDT",
            time_provider=lambda: 1773360000000,
            urlopen_fn=_FakeUrlOpen(
                responses=[
                    {"code": -2013, "msg": "Order does not exist."},
                    {"code": -2013, "msg": "Order does not exist."},
                    {"code": -2013, "msg": "Order does not exist."},
                ]
            ),
        ),
        state_store=store,
        cursor="gap-escalate",
        has_gap=True,
        occurred_at=_ts(),
    )

    snapshot = store.load_snapshot()

    final_state = [state for state in result.workflow_result.order_states if state.order_id == "escalate-1"][-1]
    assert final_state.reconciliation_state is ReconciliationState.UNRECONCILED_MANUAL_ATTENTION
    assert result.workflow_result.convergence_state == "unreconciled_manual_attention"
    assert snapshot.manual_attention_order_ids == ("escalate-1",)
    assert snapshot.last_manual_attention_at is not None
    assert "escalate-1" in snapshot.unresolved_order_ids


def _ts() -> datetime:
    return datetime(2026, 3, 13, 0, 0, tzinfo=UTC)


def _config() -> BinanceAdapterConfig:
    return BinanceAdapterConfig(
        rest_base_url="https://api.binance.com",
        websocket_base_url="wss://stream.binance.com:9443",
        api_key="key",
        api_secret="secret",
    )


def _translator() -> BinancePrivatePayloadTranslator:
    return BinancePrivatePayloadTranslator(
        symbol_mappings=(BinanceSymbolMapping(instrument_id="BTC-USDT", venue_symbol="BTCUSDT"),),
    )


def _clock_sync():
    from app.exchanges.binance import BinanceClockSync

    return BinanceClockSync(_config())


class _FakeHttpResponse:
    def __init__(self, payload: dict[str, object], status: int = 200) -> None:
        self._payload = payload
        self.status = status

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeUrlOpen:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = responses

    def __call__(self, request):
        payload = self.responses.pop(0)
        return _FakeHttpResponse(payload)
