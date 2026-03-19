"""Runtime dependency container and mode definitions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from app.contracts import BarSlice
from app.contracts import DecisionContext
from app.contracts import ExecutionIntent
from app.contracts import FeatureSnapshot
from app.contracts import IndexSnapshot
from app.contracts import PortfolioState
from app.contracts import RiskDecision
from app.contracts import RuntimeCycleResult
from app.contracts import SignalDecision
from app.contracts import StablecoinSnapshot
from app.contracts import VenueProfile
from app.monitoring.models import ExchangeHealthSnapshot
from app.portfolio import LivePortfolioMutationOutcome


class RunnerMode(str, Enum):
    """Supported runtime operating modes.

    `report_only` completes the analysis pipeline and persists reports only.
    `paper` also produces execution intents but never reaches an exchange.
    `restricted_live` prepares live-facing intents while still deferring submission.
    """

    REPORT_ONLY = "report_only"
    PAPER = "paper"
    RESTRICTED_LIVE = "restricted_live"


class FeatureBuilder(Protocol):
    """Builds strategy-facing features from a normalized bar slice."""

    def build(self, bar_slice: BarSlice, context_bar_slice: BarSlice | None = None) -> FeatureSnapshot:
        """Return a complete feature snapshot for the current bar window."""


class IndexSnapshotProvider(Protocol):
    """Provides optional precomputed index snapshots for feature composition."""

    def get_snapshot(self, *, instrument_id: str, as_of) -> IndexSnapshot | None:
        """Return an index snapshot when available for the current cycle."""


class StablecoinSnapshotProvider(Protocol):
    """Provides optional stablecoin snapshots for feature composition."""

    def get_snapshot(self, *, as_of) -> StablecoinSnapshot | None:
        """Return a stablecoin snapshot when available for the current cycle."""


class StrategyEvaluator(Protocol):
    """Evaluates one decision cycle from canonical runtime inputs."""

    def evaluate(self, context: DecisionContext) -> tuple[SignalDecision, ...]:
        """Return zero or more venue-neutral strategy decisions."""


class RiskEvaluator(Protocol):
    """Evaluates strategy decisions against runtime and portfolio rules."""

    def evaluate(
        self,
        signals: tuple[SignalDecision, ...],
        portfolio_state: PortfolioState,
        venue_profile: VenueProfile | None,
    ) -> tuple[RiskDecision, ...]:
        """Return auditable risk outcomes for the supplied signals."""


class ExecutionIntentBuilder(Protocol):
    """Builds deterministic execution intents without submitting them."""

    def build(
        self,
        *,
        risk_decisions: tuple[RiskDecision, ...],
        venue: str,
        submitted_at,
    ) -> tuple[ExecutionIntent, ...]:
        """Return executable intents with no side effects."""


class PersistenceGateway(Protocol):
    """Persists cycle artifacts for reporting, auditability, and recovery."""

    def persist_cycle(
        self,
        cycle_result: RuntimeCycleResult,
        *,
        features: FeatureSnapshot,
        context: DecisionContext,
        exchange_health: ExchangeHealthSnapshot | None = None,
        ) -> None:
        """Persist cycle artifacts produced by a runner."""


class ExchangeHealthProvider(Protocol):
    """Provides an optional operator-facing exchange health snapshot for one cycle."""

    def current_health(self) -> ExchangeHealthSnapshot | None:
        """Return the latest exchange health snapshot when available."""


class LivePortfolioMutationGate(Protocol):
    """Applies canonical live exchange updates through the mandatory safety gate."""

    def apply(
        self,
        *,
        portfolio_state: PortfolioState,
        expected_order_ids: tuple[str, ...] = (),
        already_applied_fill_ids: tuple[str, ...] = (),
    ) -> LivePortfolioMutationOutcome:
        """Return a guarded mutation outcome for restricted-live processing."""


@dataclass(frozen=True)
class RuntimeContext:
    """Injected runtime dependencies and static mode configuration.

    The context keeps mode-specific runner wiring explicit and prevents hidden
    imports between strategy, risk, execution, and exchange boundaries.
    """

    mode: RunnerMode
    feature_builder: FeatureBuilder
    strategy_evaluator: StrategyEvaluator
    risk_evaluator: RiskEvaluator
    execution_intent_builder: ExecutionIntentBuilder
    persistence_gateway: PersistenceGateway
    index_snapshot_provider: IndexSnapshotProvider | None = None
    stablecoin_snapshot_provider: StablecoinSnapshotProvider | None = None
    live_portfolio_mutation_gate: LivePortfolioMutationGate | None = None
    exchange_health_provider: ExchangeHealthProvider | None = None
    venue_profile: VenueProfile | None = None
    execution_venue: str | None = None
    time_sync_ok: bool | None = None
    time_sync_detail: str | None = None
