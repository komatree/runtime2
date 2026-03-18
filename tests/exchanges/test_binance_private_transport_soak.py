from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from pathlib import Path

from app.exchanges.binance import BinanceAdapterConfig
from app.exchanges.binance import BinancePrivateStreamClient
from app.exchanges.binance import BinancePrivateStreamSubscription
from app.exchanges.binance import BinancePrivateTransportSoakAction
from app.exchanges.binance import BinancePrivateTransportSoakArtifactWriter
from app.exchanges.binance import BinancePrivateTransportSoakReportingService
from app.exchanges.binance import BinancePrivateTransportSoakRunner
from app.exchanges.binance import BinancePrivateTransportSoakStep


def test_private_transport_soak_runner_records_reconnect_refresh_and_degradation(tmp_path) -> None:
    runner = BinancePrivateTransportSoakRunner(
        client=BinancePrivateStreamClient(config=_config()),
        heartbeat_timeout=timedelta(seconds=30),
    )
    transport = _FakeReadableTransport(
        payloads=[
            _execution_report_payload(order_id=1001),
        ]
    )
    started_at = _ts(0)
    steps = (
        BinancePrivateTransportSoakStep(
            action=BinancePrivateTransportSoakAction.READ_PAYLOAD,
            occurred_at=_ts(5),
        ),
        BinancePrivateTransportSoakStep(
            action=BinancePrivateTransportSoakAction.HEARTBEAT_CHECK,
            occurred_at=_ts(50),
        ),
        BinancePrivateTransportSoakStep(
            action=BinancePrivateTransportSoakAction.RECONNECT,
            occurred_at=_ts(60),
        ),
        BinancePrivateTransportSoakStep(
            action=BinancePrivateTransportSoakAction.REFRESH,
            occurred_at=_ts(65),
        ),
        BinancePrivateTransportSoakStep(
            action=BinancePrivateTransportSoakAction.SHUTDOWN,
            occurred_at=_ts(70),
        ),
    )

    run = runner.run(transport=transport, steps=steps, started_at=started_at)
    markdown = BinancePrivateTransportSoakReportingService().render_markdown(run=run)
    paths = BinancePrivateTransportSoakArtifactWriter(output_dir=tmp_path).persist(run=run, markdown=markdown)

    assert run.summary.reconnect_count == 1
    assert run.summary.refresh_attempts == 1
    assert run.summary.degraded_transition_count == 1
    assert run.summary.final_state.value == "shutdown"
    assert "heartbeat overdue" in markdown
    assert all(path.exists() for path in paths)
    lines = (tmp_path / "health_transitions.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == len(steps)
    assert json.loads(lines[1])["state"] == "degraded"


def test_private_transport_soak_runner_marks_refresh_failure_and_expiry(tmp_path) -> None:
    runner = BinancePrivateTransportSoakRunner(
        client=BinancePrivateStreamClient(config=_config(), session_ttl=timedelta(seconds=60)),
        heartbeat_timeout=timedelta(seconds=30),
    )
    transport = _FakeReadableTransport(payloads=[])
    started_at = _ts(0)
    steps = (
        BinancePrivateTransportSoakStep(
            action=BinancePrivateTransportSoakAction.REFRESH,
            occurred_at=_ts(61),
            transport_error="refresh timeout",
        ),
        BinancePrivateTransportSoakStep(
            action=BinancePrivateTransportSoakAction.SHUTDOWN,
            occurred_at=_ts(62),
        ),
    )

    run = runner.run(transport=transport, steps=steps, started_at=started_at)
    markdown = BinancePrivateTransportSoakReportingService().render_markdown(run=run)
    BinancePrivateTransportSoakArtifactWriter(output_dir=tmp_path).persist(run=run, markdown=markdown)

    assert run.summary.refresh_failures == 1
    assert run.summary.termination_count == 1
    assert run.transitions[0].state.value == "terminated"
    assert "subscription expired before renewal completed" in markdown


def test_private_transport_soak_script_writes_artifacts(tmp_path) -> None:
    plan_path = tmp_path / "plan.json"
    output_dir = tmp_path / "artifacts"
    plan_path.write_text(
        json.dumps(
            {
                "started_at": _ts(0).isoformat(),
                "heartbeat_timeout_seconds": 30,
                "steps": [
                    {
                        "action": "read_payload",
                        "occurred_at": _ts(5).isoformat(),
                        "payload": _execution_report_payload(order_id=2001),
                    },
                    {
                        "action": "heartbeat_check",
                        "occurred_at": _ts(45).isoformat(),
                    },
                    {
                        "action": "shutdown",
                        "occurred_at": _ts(50).isoformat(),
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(Path("scripts/binance_private_transport_soak.py")),
            "--plan",
            str(plan_path),
            "--output-dir",
            str(output_dir),
        ],
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert (output_dir / "health_transitions.jsonl").exists()
    assert (output_dir / "soak_summary.json").exists()
    assert (output_dir / "soak_summary.md").exists()


@dataclass
class _FakeReadableTransport:
    payloads: list[dict[str, object]]

    def __post_init__(self) -> None:
        self.connection_index = 0
        self.closed_connections: list[str] = []

    def open_connection(self, *, account_scope: str) -> str:
        self.connection_index += 1
        return f"private-connection-{self.connection_index}"

    def subscribe(self, *, connection_id: str, account_scope: str) -> BinancePrivateStreamSubscription:
        subscription_id = f"{account_scope}.{connection_id}.user_data_stream"
        return BinancePrivateStreamSubscription(
            subscription_id=subscription_id,
            stream_key=subscription_id,
            bootstrap_method="userDataStream.subscribe.signature",
        )

    def close_connection(self, *, connection_id: str) -> None:
        self.closed_connections.append(connection_id)

    def read_payload(self, *, connection_id: str) -> dict[str, object]:
        return self.payloads.pop(0)


def _config() -> BinanceAdapterConfig:
    return BinanceAdapterConfig(
        rest_base_url="https://api.binance.com",
        websocket_base_url="wss://stream.binance.com:9443",
    )


def _execution_report_payload(*, order_id: int) -> dict[str, object]:
    return {
        "e": "executionReport",
        "E": 1773360005000,
        "s": "BTCUSDT",
        "c": f"client-{order_id}",
        "i": order_id,
        "X": "FILLED",
        "x": "TRADE",
    }


def _ts(seconds: int) -> datetime:
    return datetime(2026, 3, 13, 0, 0, tzinfo=UTC) + timedelta(seconds=seconds)
