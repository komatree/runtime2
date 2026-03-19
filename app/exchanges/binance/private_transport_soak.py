"""Deterministic private-transport soak rehearsal for Binance adapter hardening."""

from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime
from datetime import timedelta
from enum import Enum
from pathlib import Path
from typing import Any
from typing import Protocol

from .models import BinancePrivateStreamHealth
from .models import BinancePrivateStreamSession
from .models import BinancePrivateStreamState
from .models import BinancePrivateStreamSubscription
from .private_stream_client import BinancePrivateStreamClient
from .private_stream_client import BinancePrivateStreamTransport


class BinancePrivateTransportSoakAction(str, Enum):
    """One deterministic soak action applied to the private-stream lifecycle."""

    READ_PAYLOAD = "read_payload"
    HEARTBEAT_CHECK = "heartbeat_check"
    REFRESH = "refresh"
    RECONNECT = "reconnect"
    TERMINATE = "terminate"
    SHUTDOWN = "shutdown"


@dataclass(frozen=True)
class BinancePrivateTransportSoakStep:
    """One deterministic rehearsal step.

    `transport_error` is used for failure injection. When present, the runner
    avoids calling the transport for that step and records the explicit failure.
    """

    action: BinancePrivateTransportSoakAction
    occurred_at: datetime
    payload: dict[str, object] | None = None
    reason: str | None = None
    transport_error: str | None = None


@dataclass(frozen=True)
class BinancePrivateTransportSoakTransition:
    """Persisted health transition emitted during soak rehearsal."""

    step_index: int
    action: BinancePrivateTransportSoakAction
    occurred_at: datetime
    previous_state: BinancePrivateStreamState | None
    state: BinancePrivateStreamState
    state_changed: bool
    is_authoritative: bool
    authoritative_changed: bool
    reconnect_attempts: int
    refresh_attempts: int
    refresh_failures: int
    connection_id: str | None
    stream_key: str
    alerts: tuple[str, ...]


@dataclass(frozen=True)
class BinancePrivateTransportSoakSummary:
    """Operator-facing summary for one private transport soak run."""

    started_at: datetime
    ended_at: datetime
    total_steps: int
    final_state: BinancePrivateStreamState
    reconnect_count: int
    refresh_attempts: int
    refresh_failures: int
    authoritative_transition_count: int
    degraded_transition_count: int
    termination_count: int
    alerts: tuple[str, ...]


@dataclass(frozen=True)
class BinancePrivateTransportSoakRun:
    """Full soak result including summary, transitions, and final session."""

    summary: BinancePrivateTransportSoakSummary
    transitions: tuple[BinancePrivateTransportSoakTransition, ...]
    final_session: BinancePrivateStreamSession


class BinancePrivateTransportReadable(Protocol):
    """Transport boundary required by the deterministic soak runner."""

    def open_connection(self, *, account_scope: str) -> str:
        """Return a connection identifier."""

    def subscribe(
        self,
        *,
        connection_id: str,
        account_scope: str,
    ) -> BinancePrivateStreamSubscription:
        """Return an authenticated subscription receipt."""

    def close_connection(self, *, connection_id: str) -> None:
        """Close the active connection."""

    def read_payload(self, *, connection_id: str) -> dict[str, object]:
        """Read one payload from the active connection."""


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def _unique_alerts(*groups: tuple[str, ...]) -> tuple[str, ...]:
    values: list[str] = []
    for group in groups:
        for alert in group:
            if alert not in values:
                values.append(alert)
    return tuple(values)


@dataclass(frozen=True)
class BinancePrivateTransportSoakRunner:
    """Runs deterministic private-stream soak/failure-injection rehearsals.

    This runner is intentionally rehearsal-grade:
    - explicit scripted steps instead of hidden background retries
    - append-only health transitions
    - operator visibility over reconnect, refresh, expiry, and heartbeat states
    """

    client: BinancePrivateStreamClient
    heartbeat_timeout: timedelta

    def run(
        self,
        *,
        transport: BinancePrivateTransportReadable,
        steps: tuple[BinancePrivateTransportSoakStep, ...],
        started_at: datetime,
    ) -> BinancePrivateTransportSoakRun:
        """Execute the scripted soak scenario and return durable artifacts."""

        session = self.client.bootstrap_session(transport=transport, started_at=started_at)
        transitions: list[BinancePrivateTransportSoakTransition] = []
        refresh_attempts = 0
        refresh_failures = 0
        termination_count = 0
        last_health = self.client.build_health_snapshot(session=session, occurred_at=started_at)

        for step_index, step in enumerate(steps, start=1):
            previous_state = last_health.state
            previous_authoritative = last_health.is_authoritative
            health: BinancePrivateStreamHealth

            if step.action is BinancePrivateTransportSoakAction.READ_PAYLOAD:
                if step.transport_error is not None:
                    health = BinancePrivateStreamHealth(
                        state=BinancePrivateStreamState.DEGRADED,
                        reconnect_attempts=session.reconnect_attempts,
                        last_message_at=session.last_message_at,
                        session_expires_at=session.expires_at,
                        is_authoritative=False,
                        alerts=(f"private transport read failed: {step.transport_error}",),
                    )
                else:
                    payload = step.payload
                    if payload is None:
                        payload = transport.read_payload(connection_id=session.connection_id or "")
                    batch = self.client.ingest_payloads(payloads=(payload,))
                    if batch.stream_state is BinancePrivateStreamState.TERMINATED:
                        termination_count += 1
                        session = replace(
                            session,
                            state=BinancePrivateStreamState.TERMINATED,
                            last_message_at=batch.last_event_time or step.occurred_at,
                            alerts=_unique_alerts(session.alerts, batch.alerts),
                        )
                    else:
                        session = self.client.mark_streaming(session=session, occurred_at=step.occurred_at)
                    health = self.client.build_health_snapshot(
                        session=session,
                        batch=batch,
                        occurred_at=step.occurred_at,
                    )

            elif step.action is BinancePrivateTransportSoakAction.HEARTBEAT_CHECK:
                if session.expires_at is not None and step.occurred_at >= session.expires_at:
                    termination_count += 1
                    health = self.client.terminated_stream_health(
                        occurred_at=step.occurred_at,
                        reason="subscription_expired",
                    )
                    session = replace(
                        session,
                        state=BinancePrivateStreamState.TERMINATED,
                        last_message_at=step.occurred_at,
                        alerts=_unique_alerts(session.alerts, health.alerts),
                    )
                elif session.last_message_at is None or (
                    step.occurred_at - session.last_message_at
                ) > self.heartbeat_timeout:
                    health = BinancePrivateStreamHealth(
                        state=BinancePrivateStreamState.DEGRADED,
                        reconnect_attempts=session.reconnect_attempts,
                        last_message_at=session.last_message_at,
                        session_expires_at=session.expires_at,
                        is_authoritative=False,
                        alerts=("private stream heartbeat overdue",),
                    )
                else:
                    health = self.client.build_health_snapshot(
                        session=session,
                        occurred_at=step.occurred_at,
                    )

            elif step.action is BinancePrivateTransportSoakAction.REFRESH:
                refresh_attempts += 1
                if step.transport_error is not None:
                    refresh_failures += 1
                    expired = session.expires_at is not None and step.occurred_at >= session.expires_at
                    if expired:
                        termination_count += 1
                    health = BinancePrivateStreamHealth(
                        state=(
                            BinancePrivateStreamState.TERMINATED
                            if expired
                            else BinancePrivateStreamState.DEGRADED
                        ),
                        reconnect_attempts=session.reconnect_attempts,
                        last_message_at=session.last_message_at,
                        session_expires_at=session.expires_at,
                        is_authoritative=False,
                        alerts=(
                            f"private stream subscription renewal failed: {step.transport_error}",
                            *(
                                ("private stream subscription expired before renewal completed",)
                                if expired
                                else ()
                            ),
                        ),
                    )
                    session = replace(
                        session,
                        state=health.state,
                        alerts=_unique_alerts(session.alerts, health.alerts),
                    )
                else:
                    session = self.client.refresh_session(
                        session=session,
                        occurred_at=step.occurred_at,
                        transport=transport,
                    )
                    health = self.client.build_health_snapshot(
                        session=session,
                        occurred_at=step.occurred_at,
                    )
                    health = BinancePrivateStreamHealth(
                        state=health.state,
                        reconnect_attempts=health.reconnect_attempts,
                        last_message_at=health.last_message_at,
                        last_reconnect_at=health.last_reconnect_at,
                        session_expires_at=health.session_expires_at,
                        is_authoritative=health.is_authoritative,
                        alerts=_unique_alerts(health.alerts, ("private stream subscription renewed",)),
                    )

            elif step.action is BinancePrivateTransportSoakAction.RECONNECT:
                if step.transport_error is not None:
                    health = BinancePrivateStreamHealth(
                        state=BinancePrivateStreamState.DEGRADED,
                        reconnect_attempts=session.reconnect_attempts + 1,
                        last_message_at=session.last_message_at,
                        last_reconnect_at=step.occurred_at,
                        session_expires_at=session.expires_at,
                        is_authoritative=False,
                        alerts=(f"private stream reconnect failed: {step.transport_error}",),
                    )
                    session = replace(
                        session,
                        reconnect_attempts=session.reconnect_attempts + 1,
                        alerts=_unique_alerts(session.alerts, health.alerts),
                    )
                else:
                    session = self.client.reconnect_session(
                        session=session,
                        occurred_at=step.occurred_at,
                        transport=transport,
                    )
                    health = self.client.on_reconnect(
                        session=replace(session, reconnect_attempts=session.reconnect_attempts - 1),
                        occurred_at=step.occurred_at,
                        connection_id=session.connection_id,
                    )

            elif step.action is BinancePrivateTransportSoakAction.TERMINATE:
                termination_count += 1
                health = self.client.terminated_stream_health(
                    occurred_at=step.occurred_at,
                    reason=step.reason or "manual_termination",
                )
                session = replace(
                    session,
                    state=BinancePrivateStreamState.TERMINATED,
                    last_message_at=step.occurred_at,
                    alerts=_unique_alerts(session.alerts, health.alerts),
                )

            elif step.action is BinancePrivateTransportSoakAction.SHUTDOWN:
                health = self.client.shutdown(
                    session=session,
                    occurred_at=step.occurred_at,
                    transport=transport,
                )
                session = replace(
                    session,
                    state=BinancePrivateStreamState.SHUTDOWN,
                    last_message_at=step.occurred_at,
                    alerts=_unique_alerts(session.alerts, health.alerts),
                )

            else:
                raise ValueError(f"unsupported soak action: {step.action}")

            transitions.append(
                BinancePrivateTransportSoakTransition(
                    step_index=step_index,
                    action=step.action,
                    occurred_at=step.occurred_at,
                    previous_state=previous_state,
                    state=health.state,
                    state_changed=previous_state is not health.state,
                    is_authoritative=health.is_authoritative,
                    authoritative_changed=previous_authoritative is not health.is_authoritative,
                    reconnect_attempts=health.reconnect_attempts,
                    refresh_attempts=refresh_attempts,
                    refresh_failures=refresh_failures,
                    connection_id=session.connection_id,
                    stream_key=session.stream_key,
                    alerts=_unique_alerts(session.alerts, health.alerts),
                )
            )
            last_health = health

        ended_at = steps[-1].occurred_at if steps else started_at
        summary = BinancePrivateTransportSoakSummary(
            started_at=started_at,
            ended_at=ended_at,
            total_steps=len(steps),
            final_state=last_health.state,
            reconnect_count=session.reconnect_attempts,
            refresh_attempts=refresh_attempts,
            refresh_failures=refresh_failures,
            authoritative_transition_count=sum(1 for item in transitions if item.is_authoritative),
            degraded_transition_count=sum(
                1 for item in transitions if item.state is BinancePrivateStreamState.DEGRADED
            ),
            termination_count=termination_count,
            alerts=_unique_alerts(*(item.alerts for item in transitions)),
        )
        return BinancePrivateTransportSoakRun(
            summary=summary,
            transitions=tuple(transitions),
            final_session=session,
        )


@dataclass(frozen=True)
class BinancePrivateTransportSoakReportingService:
    """Builds operator-readable markdown for private transport soak runs."""

    def render_markdown(self, *, run: BinancePrivateTransportSoakRun) -> str:
        """Render a concise operator-facing soak summary."""

        alerts = ", ".join(run.summary.alerts) or "none"
        return "\n".join(
            [
                "# Binance Private Transport Soak Summary",
                f"- started_at: {run.summary.started_at.isoformat()}",
                f"- ended_at: {run.summary.ended_at.isoformat()}",
                f"- total_steps: {run.summary.total_steps}",
                f"- final_state: {run.summary.final_state.value}",
                f"- reconnect_count: {run.summary.reconnect_count}",
                f"- refresh_attempts: {run.summary.refresh_attempts}",
                f"- refresh_failures: {run.summary.refresh_failures}",
                f"- authoritative_transition_count: {run.summary.authoritative_transition_count}",
                f"- degraded_transition_count: {run.summary.degraded_transition_count}",
                f"- termination_count: {run.summary.termination_count}",
                f"- alerts: {alerts}",
            ]
        )


@dataclass(frozen=True)
class BinancePrivateTransportSoakArtifactWriter:
    """Persists append-only soak transitions and final summary artifacts."""

    output_dir: Path

    def persist(self, *, run: BinancePrivateTransportSoakRun, markdown: str) -> tuple[Path, Path, Path]:
        """Write JSONL transitions plus JSON and markdown summaries."""

        self.output_dir.mkdir(parents=True, exist_ok=True)
        transitions_path = self.output_dir / "health_transitions.jsonl"
        summary_json_path = self.output_dir / "soak_summary.json"
        summary_markdown_path = self.output_dir / "soak_summary.md"

        with transitions_path.open("a", encoding="utf-8") as handle:
            for transition in run.transitions:
                handle.write(json.dumps(asdict(transition), default=_json_default, sort_keys=True))
                handle.write("\n")

        summary_json_path.write_text(
            json.dumps(asdict(run.summary), default=_json_default, sort_keys=True),
            encoding="utf-8",
        )
        summary_markdown_path.write_text(markdown, encoding="utf-8")
        return transitions_path, summary_json_path, summary_markdown_path
