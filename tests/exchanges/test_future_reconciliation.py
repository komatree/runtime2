"""Future reconciliation baseline tests.

TODO:
- Replace stubs with canonical order-state and fill-event reconciliation checks.
- Add REST fallback, sequence-gap recovery, and unknown execution escalation tests.
"""

from datetime import UTC
from datetime import datetime

from app.exchanges.binance import BinancePrivateEventFamily
from app.exchanges.binance import BinancePrivateStreamEvent
from app.exchanges.binance import BinanceReconciliationService


def test_future_reconciliation_unknown_execution_placeholder() -> None:
    service = BinanceReconciliationService()
    result = service.reconcile(
        expected_order_ids=("expected-1",),
        private_events=(
            BinancePrivateStreamEvent(
                event_type="execution_report",
                event_family=BinancePrivateEventFamily.ORDER_UPDATE,
                event_time=datetime(2026, 3, 12, 0, 0, tzinfo=UTC),
                account_scope="spot",
                sequence_id="unexpected-order",
            ),
        ),
    )

    assert result.matched_order_ids == ()
    assert result.missing_order_ids == ("expected-1",)
    assert isinstance(result.alerts, tuple)
