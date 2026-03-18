#!/usr/bin/env python3
"""Run a deterministic Binance private transport soak rehearsal from a JSON plan."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.exchanges.binance import BinanceAdapterConfig
from app.exchanges.binance import BinancePrivateStreamClient
from app.exchanges.binance import BinancePrivateStreamSubscription
from app.exchanges.binance.private_transport_soak import BinancePrivateTransportSoakAction
from app.exchanges.binance.private_transport_soak import BinancePrivateTransportSoakArtifactWriter
from app.exchanges.binance.private_transport_soak import BinancePrivateTransportSoakReportingService
from app.exchanges.binance.private_transport_soak import BinancePrivateTransportSoakRunner
from app.exchanges.binance.private_transport_soak import BinancePrivateTransportSoakStep


class _PlanDrivenTransport:
    """Deterministic transport used for soak rehearsal and failure injection."""

    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self._payloads = payloads
        self._connection_index = 0

    def open_connection(self, *, account_scope: str) -> str:
        self._connection_index += 1
        return f"private-connection-{self._connection_index}"

    def subscribe(self, *, connection_id: str, account_scope: str) -> BinancePrivateStreamSubscription:
        subscription_id = f"{account_scope}.{connection_id}.user_data_stream"
        return BinancePrivateStreamSubscription(
            subscription_id=subscription_id,
            stream_key=subscription_id,
            bootstrap_method="userDataStream.subscribe.signature",
        )

    def close_connection(self, *, connection_id: str) -> None:
        return None

    def read_payload(self, *, connection_id: str) -> dict[str, object]:
        if not self._payloads:
            raise RuntimeError(f"no scripted payloads remain for {connection_id}")
        return self._payloads.pop(0)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="runtime2 Binance private transport soak runner")
    parser.add_argument("--plan", required=True, help="Path to the soak plan JSON file.")
    parser.add_argument("--output-dir", required=True, help="Directory for soak artifacts.")
    return parser.parse_args()


def _load_steps(payload: dict[str, object]) -> tuple[datetime, timedelta, tuple[BinancePrivateTransportSoakStep, ...], list[dict[str, object]]]:
    started_at = datetime.fromisoformat(str(payload["started_at"]))
    heartbeat_timeout = timedelta(seconds=int(payload.get("heartbeat_timeout_seconds", 30)))
    steps: list[BinancePrivateTransportSoakStep] = []
    scripted_payloads: list[dict[str, object]] = []
    for raw_step in payload.get("steps", ()):
        if not isinstance(raw_step, dict):
            raise ValueError("each soak step must be an object")
        step_payload = raw_step.get("payload")
        if isinstance(step_payload, dict):
            scripted_payloads.append(step_payload)
        steps.append(
            BinancePrivateTransportSoakStep(
                action=BinancePrivateTransportSoakAction(str(raw_step["action"])),
                occurred_at=datetime.fromisoformat(str(raw_step["occurred_at"])),
                payload=step_payload if isinstance(step_payload, dict) else None,
                reason=str(raw_step["reason"]) if raw_step.get("reason") is not None else None,
                transport_error=(
                    str(raw_step["transport_error"])
                    if raw_step.get("transport_error") is not None
                    else None
                ),
            )
        )
    return started_at, heartbeat_timeout, tuple(steps), scripted_payloads


def main() -> int:
    args = _parse_args()
    plan_path = Path(args.plan)
    output_dir = Path(args.output_dir)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))

    started_at, heartbeat_timeout, steps, scripted_payloads = _load_steps(plan)
    config = BinanceAdapterConfig(
        rest_base_url="https://api.binance.com",
        websocket_base_url="wss://stream.binance.com:9443",
    )
    runner = BinancePrivateTransportSoakRunner(
        client=BinancePrivateStreamClient(config=config),
        heartbeat_timeout=heartbeat_timeout,
    )
    run = runner.run(
        transport=_PlanDrivenTransport(payloads=scripted_payloads),
        steps=steps,
        started_at=started_at,
    )
    markdown = BinancePrivateTransportSoakReportingService().render_markdown(run=run)
    BinancePrivateTransportSoakArtifactWriter(output_dir=output_dir).persist(run=run, markdown=markdown)
    print(markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
