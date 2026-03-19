"""Pure precision and venue-constraint helpers.

Adapted selectively from the local legacy reference utilities and rewritten for
`runtime2` using `Decimal` and venue-neutral naming.
"""

from __future__ import annotations

from decimal import ROUND_DOWN
from decimal import Decimal


def snap_to_increment(value: Decimal, increment: Decimal) -> Decimal:
    """Floor `value` to the nearest lower multiple of `increment`.

    Returns `0` when `value <= 0`. Raises on non-positive increments.
    """

    if increment <= Decimal("0"):
        raise ValueError("increment must be positive")
    if value <= Decimal("0"):
        return Decimal("0")
    steps = (value / increment).to_integral_value(rounding=ROUND_DOWN)
    return steps * increment


def select_preferred_step_size(
    market_step_size: Decimal | None,
    lot_step_size: Decimal | None,
) -> Decimal | None:
    """Prefer market-specific step size and fall back to generic lot size."""

    if market_step_size is not None and market_step_size > Decimal("0"):
        return market_step_size
    if lot_step_size is not None and lot_step_size > Decimal("0"):
        return lot_step_size
    return None


def meets_min_notional(
    *,
    quantity: Decimal,
    price: Decimal,
    min_notional: Decimal | None,
) -> bool:
    """Return whether a quantity/price pair satisfies the minimum notional."""

    if min_notional is None or min_notional <= Decimal("0"):
        return True
    return quantity * price >= min_notional
