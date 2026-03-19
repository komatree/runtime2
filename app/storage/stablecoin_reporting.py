"""Append-only storage and reporting for stablecoin observability snapshots."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.contracts import StablecoinSnapshot


def _stablecoin_json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


@dataclass(frozen=True)
class StablecoinSnapshotStorage:
    """Append-only JSONL/CSV/Markdown storage for stablecoin observability."""

    jsonl_path: Path
    csv_path: Path
    markdown_path: Path

    def append(self, snapshot: StablecoinSnapshot) -> None:
        """Append one snapshot to JSONL/CSV and refresh markdown summary."""

        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        self.markdown_path.parent.mkdir(parents=True, exist_ok=True)
        self._append_jsonl(snapshot)
        self._append_csv(snapshot)
        self._write_markdown(snapshot)

    def read_latest(self) -> StablecoinSnapshot | None:
        """Read the latest stored snapshot from JSONL."""

        if not self.jsonl_path.exists():
            return None
        lines = [line for line in self.jsonl_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            return None
        payload = json.loads(lines[-1])
        return StablecoinSnapshot(
            pair=payload["pair"],
            reference_asset=payload["reference_asset"],
            snapshot_version=payload["snapshot_version"],
            source_type=payload["source_type"],
            as_of=datetime.fromisoformat(payload["as_of"]),
            source_fresh_until=datetime.fromisoformat(payload["source_fresh_until"]),
            stablecoin_net_mint_24h=Decimal(payload["stablecoin_net_mint_24h"]),
            stablecoin_net_burn_24h=Decimal(payload["stablecoin_net_burn_24h"]),
            stablecoin_supply_change_pct_24h=Decimal(payload["stablecoin_supply_change_pct_24h"]),
            stablecoin_chain_supply_delta_24h=Decimal(payload["stablecoin_chain_supply_delta_24h"]),
            stablecoin_abnormal_transfer_count=int(payload["stablecoin_abnormal_transfer_count"]),
            price=Decimal(payload["price"]) if payload.get("price") is not None else None,
            premium_bps=Decimal(payload["premium_bps"]) if payload.get("premium_bps") is not None else None,
            volume_24h=Decimal(payload["volume_24h"]) if payload.get("volume_24h") is not None else None,
            liquidity_score=Decimal(payload["liquidity_score"]) if payload.get("liquidity_score") is not None else None,
            is_depegged=bool(payload["is_depegged"]),
        )

    def _append_jsonl(self, snapshot: StablecoinSnapshot) -> None:
        with self.jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(snapshot), default=_stablecoin_json_default, sort_keys=True))
            handle.write("\n")

    def _append_csv(self, snapshot: StablecoinSnapshot) -> None:
        row = {
            "as_of": snapshot.as_of.isoformat(),
            "source_fresh_until": snapshot.source_fresh_until.isoformat(),
            "source_type": snapshot.source_type,
            "snapshot_version": snapshot.snapshot_version,
            "pair": snapshot.pair,
            "reference_asset": snapshot.reference_asset,
            "stablecoin_net_mint_24h": str(snapshot.stablecoin_net_mint_24h),
            "stablecoin_net_burn_24h": str(snapshot.stablecoin_net_burn_24h),
            "stablecoin_supply_change_pct_24h": str(snapshot.stablecoin_supply_change_pct_24h),
            "stablecoin_chain_supply_delta_24h": str(snapshot.stablecoin_chain_supply_delta_24h),
            "stablecoin_abnormal_transfer_count": str(snapshot.stablecoin_abnormal_transfer_count),
        }
        write_header = not self.csv_path.exists()
        with self.csv_path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=tuple(row.keys()))
            if write_header:
                writer.writeheader()
            writer.writerow(row)

    def _write_markdown(self, snapshot: StablecoinSnapshot) -> None:
        self.markdown_path.write_text(
            "\n".join(
                [
                    "# Stablecoin Observability Summary",
                    "",
                    f"- `as_of`: {snapshot.as_of.isoformat()}",
                    f"- `source_type`: {snapshot.source_type}",
                    f"- `source_fresh_until`: {snapshot.source_fresh_until.isoformat()}",
                    f"- `snapshot_version`: {snapshot.snapshot_version}",
                    f"- `pair`: {snapshot.pair}",
                    f"- `stablecoin_net_mint_24h`: {snapshot.stablecoin_net_mint_24h}",
                    f"- `stablecoin_net_burn_24h`: {snapshot.stablecoin_net_burn_24h}",
                    f"- `stablecoin_supply_change_pct_24h`: {snapshot.stablecoin_supply_change_pct_24h}",
                    f"- `stablecoin_chain_supply_delta_24h`: {snapshot.stablecoin_chain_supply_delta_24h}",
                    f"- `stablecoin_abnormal_transfer_count`: {snapshot.stablecoin_abnormal_transfer_count}",
                ]
            ),
            encoding="utf-8",
        )
