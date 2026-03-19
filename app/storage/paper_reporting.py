"""Paper-mode state transition persistence."""

from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.contracts import FillEvent
from app.contracts import OrderState
from app.contracts import PositionState
from app.contracts import PortfolioState


def _paper_json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


@dataclass(frozen=True)
class JsonlPaperStatePersistenceGateway:
    """Appends explicit paper-mode state transitions as JSONL."""

    output_path: Path
    summary_output_path: Path | None = None

    def persist_transition(
        self,
        *,
        cycle_id: str,
        starting_portfolio_state: PortfolioState,
        ending_portfolio_state: PortfolioState,
        order_states: tuple[OrderState, ...],
        fill_events: tuple[FillEvent, ...],
    ) -> None:
        """Persist simulated order/fill and portfolio transition details."""

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "paper_state_transition.v1",
            "cycle_id": cycle_id,
            "starting_portfolio_state": asdict(starting_portfolio_state),
            "ending_portfolio_state": asdict(ending_portfolio_state),
            "order_states": [asdict(item) for item in order_states],
            "fill_events": [asdict(item) for item in fill_events],
        }
        with self.output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, default=_paper_json_default, sort_keys=True))
            handle.write("\n")

    def persist_session_summary(
        self,
        *,
        session_id: str,
        cycle_ids: tuple[str, ...],
        final_portfolio_state: PortfolioState,
        final_position_states: tuple[PositionState, ...],
        total_cycles: int,
        action_cycle_count: int,
    ) -> None:
        """Persist a summary record for a reproducible paper session."""

        if self.summary_output_path is None:
            return
        self.summary_output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "paper_session_summary.v1",
            "session_id": session_id,
            "cycle_ids": cycle_ids,
            "total_cycles": total_cycles,
            "action_cycle_count": action_cycle_count,
            "final_portfolio_state": asdict(final_portfolio_state),
            "final_position_states": [asdict(item) for item in final_position_states],
        }
        with self.summary_output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, default=_paper_json_default, sort_keys=True))
            handle.write("\n")
