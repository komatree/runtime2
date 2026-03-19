"""Validation utilities for closed-bar triggers."""

from __future__ import annotations

from dataclasses import dataclass

from app.contracts import BarSlice


@dataclass(frozen=True)
class BarCloseValidationResult:
    """Validation outcome for an incoming normalized candle slice.

    `is_valid=True` means the slice is safe to drive a decision cycle.
    `reasons` is always populated when validation fails.
    """

    is_valid: bool
    reasons: tuple[str, ...] = ()


class BarCloseValidator:
    """Validates that a runtime trigger corresponds to a completed bar close."""

    def validate(self, bar_slice: BarSlice) -> BarCloseValidationResult:
        """Return whether the bar slice is eligible to trigger a runtime cycle."""

        last_candle = bar_slice.candles[-1]
        reasons: list[str] = []
        if not last_candle.is_closed:
            reasons.append("latest candle is not closed")
        if bar_slice.end_time != last_candle.close_time:
            reasons.append("bar slice end_time does not match latest candle close_time")
        for previous, current in zip(bar_slice.candles, bar_slice.candles[1:]):
            if previous.close_time > current.open_time:
                reasons.append("candle windows overlap within bar slice")
                break
        if reasons:
            return BarCloseValidationResult(is_valid=False, reasons=tuple(reasons))
        return BarCloseValidationResult(is_valid=True, reasons=())
