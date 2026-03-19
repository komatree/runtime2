"""Deterministic report-only risk evaluator."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.contracts import PortfolioState
from app.contracts import RiskDecision
from app.contracts import RiskDecisionStatus
from app.contracts import SignalDecision
from app.contracts import SignalSide
from app.contracts import VenueProfile


@dataclass(frozen=True)
class ReportOnlyRiskEvaluator:
    """Applies minimal checks while preserving full report output."""

    max_notional: Decimal = Decimal("1000000")

    def evaluate(
        self,
        signals: tuple[SignalDecision, ...],
        portfolio_state: PortfolioState,
        venue_profile: VenueProfile | None,
    ) -> tuple[RiskDecision, ...]:
        """Return deterministic placeholder risk decisions."""

        decisions: list[RiskDecision] = []
        for signal in signals:
            if signal.side is SignalSide.FLAT:
                decisions.append(
                    RiskDecision(
                        signal=signal,
                        status=RiskDecisionStatus.ALLOW,
                        evaluated_at=signal.as_of,
                        reasons=("context-only signal recorded",),
                        approved_quantity=signal.target_quantity or Decimal("0"),
                    )
                )
                continue

            target_notional = signal.target_notional or Decimal("0")
            if target_notional > self.max_notional:
                decisions.append(
                    RiskDecision(
                        signal=signal,
                        status=RiskDecisionStatus.REJECT,
                        evaluated_at=signal.as_of,
                        reasons=("target notional exceeds report-only safety bound",),
                        rule_hits=("max_notional",),
                    )
                )
                continue

            decisions.append(
                RiskDecision(
                    signal=signal,
                    status=RiskDecisionStatus.ALLOW,
                    evaluated_at=signal.as_of,
                    reasons=("report-only placeholder allow",),
                    approved_notional=signal.target_notional,
                    approved_quantity=signal.target_quantity,
                    rule_hits=("report_only_placeholder",),
                )
            )
        return tuple(decisions)
