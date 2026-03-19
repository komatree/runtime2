"""Report-oriented stablecoin feature service."""

from __future__ import annotations

from decimal import Decimal

from app.contracts import BarSlice
from app.contracts import IndexSnapshot
from app.contracts import StablecoinSnapshot

from app.features.base import FeatureBundle


class StablecoinFeatureService:
    """Maps stablecoin health snapshots into report-only feature values.

    This service does not produce trading direction by itself. It exposes
    snapshot-oriented context for downstream reporting, strategy gating, or risk
    consumption without coupling to any single venue.
    """

    def build(
        self,
        *,
        bar_slice: BarSlice,
        index_snapshot: IndexSnapshot | None = None,
        stablecoin_snapshot: StablecoinSnapshot | None = None,
    ) -> FeatureBundle:
        """Build snapshot-oriented stablecoin context features when available."""

        if stablecoin_snapshot is None:
            return FeatureBundle(
                feature_values={},
                is_complete=False,
                source_bar_count=len(bar_slice.candles),
                missing_inputs=("stablecoin_snapshot",),
            )

        feature_values = {
            "stablecoin.net_mint_24h": stablecoin_snapshot.stablecoin_net_mint_24h,
            "stablecoin.net_burn_24h": stablecoin_snapshot.stablecoin_net_burn_24h,
            "stablecoin.supply_change_pct_24h": stablecoin_snapshot.stablecoin_supply_change_pct_24h,
            "stablecoin.chain_supply_delta_24h": stablecoin_snapshot.stablecoin_chain_supply_delta_24h,
            "stablecoin.abnormal_transfer_count": Decimal(stablecoin_snapshot.stablecoin_abnormal_transfer_count),
            "stablecoin.snapshot_present": Decimal("1"),
            "stablecoin.is_depegged": Decimal("1")
            if stablecoin_snapshot.is_depegged
            else Decimal("0"),
        }
        if stablecoin_snapshot.price is not None:
            feature_values["stablecoin.price"] = stablecoin_snapshot.price
        if stablecoin_snapshot.premium_bps is not None:
            feature_values["stablecoin.premium_bps"] = stablecoin_snapshot.premium_bps
        if stablecoin_snapshot.volume_24h is not None:
            feature_values["stablecoin.volume_24h"] = stablecoin_snapshot.volume_24h
        if stablecoin_snapshot.liquidity_score is not None:
            feature_values["stablecoin.liquidity_score"] = stablecoin_snapshot.liquidity_score
        feature_values["stablecoin.source_fresh"] = (
            Decimal("1") if stablecoin_snapshot.source_fresh_until >= bar_slice.end_time else Decimal("0")
        )

        return FeatureBundle(
            feature_values=feature_values,
            is_complete=True,
            source_bar_count=len(bar_slice.candles),
            missing_inputs=(),
        )
