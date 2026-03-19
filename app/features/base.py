"""Shared feature-layer abstractions and composition helpers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.contracts import BarSlice
from app.contracts import FeatureSnapshot
from app.contracts import IndexSnapshot
from app.contracts import StablecoinSnapshot


class FeatureService(Protocol):
    """Produces a partial feature mapping from canonical inputs."""

    def build(
        self,
        *,
        bar_slice: BarSlice,
        index_snapshot: IndexSnapshot | None = None,
        stablecoin_snapshot: StablecoinSnapshot | None = None,
    ) -> "FeatureBundle":
        """Build a partial feature bundle for downstream composition."""


@dataclass(frozen=True)
class FeatureBundle:
    """Partial feature output from one service before unified composition.

    `feature_values` must contain canonical feature names and Decimal values.
    `is_complete` describes whether this service had all inputs it expects.
    `missing_inputs` explains absent optional or required upstream dependencies.
    """

    feature_values: dict[str, Decimal]
    is_complete: bool
    source_bar_count: int = 0
    missing_inputs: tuple[str, ...] = ()


@dataclass(frozen=True)
class FeatureComposer:
    """Composes multiple partial feature bundles into one FeatureSnapshot.

    The composer keeps producer and consumer separation explicit: individual
    services own computation, while the composer owns the unified strategy-facing
    snapshot contract.
    """

    tolerate_partial: bool = True

    def compose(
        self,
        *,
        instrument_id: str,
        timeframe: str,
        as_of,
        bundles: tuple[FeatureBundle, ...],
    ) -> FeatureSnapshot:
        """Merge service outputs into one unified FeatureSnapshot."""

        feature_values: dict[str, Decimal] = {}
        source_bar_count = 0
        is_complete = True
        for bundle in bundles:
            feature_values.update(bundle.feature_values)
            source_bar_count = max(source_bar_count, bundle.source_bar_count)
            is_complete = is_complete and bundle.is_complete

        if not bundles:
            raise ValueError("bundles must contain at least one feature bundle")
        if source_bar_count <= 0:
            source_bar_count = 1
        return FeatureSnapshot(
            instrument_id=instrument_id,
            timeframe=timeframe,
            as_of=as_of,
            feature_values=feature_values,
            source_bar_count=source_bar_count,
            is_complete=is_complete or self.tolerate_partial,
        )
