"""Local candle-derived feature service."""

from __future__ import annotations

from decimal import Decimal

from app.contracts import BarSlice
from app.contracts import IndexSnapshot
from app.contracts import StablecoinSnapshot

from app.features.base import FeatureBundle


class CandleFeatureService:
    """Builds venue-neutral features from local candle history only.

    This service must not depend on exchange payloads or external market-wide
    signals. It is the foundational feature producer for report-only and future
    trading modes.
    """

    def build(
        self,
        *,
        bar_slice: BarSlice,
        index_snapshot: IndexSnapshot | None = None,
        stablecoin_snapshot: StablecoinSnapshot | None = None,
    ) -> FeatureBundle:
        """Build candle-derived features from the supplied normalized bar slice."""

        candles = bar_slice.candles
        latest = candles[-1]
        previous = candles[-2] if len(candles) > 1 else latest
        close_return = Decimal("0")
        if previous.close != Decimal("0"):
            close_return = (latest.close - previous.close) / previous.close
        range_ratio = Decimal("0")
        if latest.open != Decimal("0"):
            range_ratio = (latest.high - latest.low) / latest.open

        feature_values = {
            "candle.close": latest.close,
            "candle.volume": latest.volume,
            "candle.close_return_1": close_return,
            "candle.range_ratio": range_ratio,
            "candle.is_closed": Decimal("1") if latest.is_closed else Decimal("0"),
        }
        return FeatureBundle(
            feature_values=feature_values,
            is_complete=latest.is_closed,
            source_bar_count=len(candles),
            missing_inputs=(),
        )
