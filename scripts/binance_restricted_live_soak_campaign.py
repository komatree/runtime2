#!/usr/bin/env python3
"""Run a 6h/12h/24h restricted-live soak campaign."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from scripts.binance_restricted_live_soak import main as run_single_soak


DEFAULT_DURATIONS_HOURS = (6, 12, 24)


@dataclass(frozen=True)
class SoakCampaignSession:
    """One long-running restricted-live soak session in the campaign."""

    duration_hours: int
    session_id: str


def build_campaign_sessions(*, campaign_id: str) -> tuple[SoakCampaignSession, ...]:
    """Return the default 6h/12h/24h soak sessions."""

    return tuple(
        SoakCampaignSession(
            duration_hours=duration,
            session_id=f"{campaign_id}-{duration}h",
        )
        for duration in DEFAULT_DURATIONS_HOURS
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="restricted-live Binance soak campaign")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--execution-data", required=True, type=Path)
    parser.add_argument("--context-data", required=True, type=Path)
    parser.add_argument("--reports-dir", required=True, type=Path)
    parser.add_argument("--logs-dir", required=True, type=Path)
    parser.add_argument("--exchange-mode", required=True)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--cycles", type=int, default=1000000)
    parser.add_argument("--poll-interval-seconds", type=float, default=30.0)
    parser.add_argument("--max-blocked-mutations", type=int, default=3)
    parser.add_argument("--confirm-rehearsal-only", action="store_true")
    parser.add_argument("--allow-restricted-live-rehearsal", action="store_true")
    parser.add_argument("--confirm-no-order-submission", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sessions = build_campaign_sessions(campaign_id=args.campaign_id)
    exit_code = 0

    for session in sessions:
        session_args = [
            "--config",
            str(args.config),
            "--execution-data",
            str(args.execution_data),
            "--context-data",
            str(args.context_data),
            "--reports-dir",
            str(args.reports_dir),
            "--logs-dir",
            str(args.logs_dir),
            "--exchange-mode",
            args.exchange_mode,
            "--run-id",
            session.session_id,
            "--cycles",
            str(args.cycles),
            "--duration-hours",
            str(session.duration_hours),
            "--poll-interval-seconds",
            str(args.poll_interval_seconds),
            "--output-subdir",
            "soak_sessions",
            "--max-blocked-mutations",
            str(args.max_blocked_mutations),
        ]
        if args.confirm_rehearsal_only:
            session_args.append("--confirm-rehearsal-only")
        if args.allow_restricted_live_rehearsal:
            session_args.append("--allow-restricted-live-rehearsal")
        if args.confirm_no_order_submission:
            session_args.append("--confirm-no-order-submission")

        session_exit = run_single_soak(session_args)
        if session_exit != 0:
            exit_code = session_exit
            break

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
