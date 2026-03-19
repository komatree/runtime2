"""Binance market data ingestion skeleton."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from typing import Sequence

from app.contracts import BarSlice
from app.contracts import Candle

from .error_classifier import classify_binance_http_error
from .models import BinanceAdapterConfig
from .models import BinanceClientError
from .models import BinanceKlineStreamMessage
from .models import BinanceMarketDataHealth
from .models import BinancePublicMarketDataEvent
from .models import BinancePublicStreamState
from .models import BinanceReportOnlyMarketContext
from .models import BinanceSymbolMapping


@dataclass(frozen=True)
class BinanceMarketDataClient:
    """Stub for public market data ingestion.

    Responsibilities:
    - subscribe to public market data streams
    - fetch bootstrap metadata or candles when needed
    - normalize Binance symbols at the adapter boundary

    Pre-live blockers:
    - websocket connection management is not implemented
    - rate-limit handling is not implemented
    - public payload normalization to canonical market events is not implemented
    """

    config: BinanceAdapterConfig
    symbol_mappings: tuple[BinanceSymbolMapping, ...] = ()

    def describe_market_data_ingestion(self) -> str:
        """Return a short description of the intended ingestion responsibilities."""

        return "public market data ingestion placeholder"

    def normalize_kline_stream_message(
        self,
        *,
        payload: dict[str, object],
        instrument_id: str,
    ) -> BinanceKlineStreamMessage:
        """Normalize a Binance websocket kline payload into a canonical candle event."""

        data = payload.get("data", payload)
        if not isinstance(data, dict) or data.get("e") != "kline":
            raise ValueError("payload does not contain a Binance kline event")
        kline = data.get("k")
        if not isinstance(kline, dict):
            raise ValueError("payload missing kline body")

        candle = Candle(
            instrument_id=instrument_id,
            timeframe=str(kline["i"]),
            open_time=datetime.fromtimestamp(int(kline["t"]) / 1000, tz=UTC),
            close_time=datetime.fromtimestamp(int(kline["T"]) / 1000, tz=UTC),
            open=Decimal(str(kline["o"])),
            high=Decimal(str(kline["h"])),
            low=Decimal(str(kline["l"])),
            close=Decimal(str(kline["c"])),
            volume=Decimal(str(kline["v"])),
            quote_volume=Decimal(str(kline.get("q", "0"))),
            trade_count=int(kline.get("n", 0)),
            is_closed=bool(kline["x"]),
        )
        return BinanceKlineStreamMessage(
            venue_symbol=str(data.get("s", self.to_venue_symbol(instrument_id))),
            timeframe=str(kline["i"]),
            event_time=datetime.fromtimestamp(int(data["E"]) / 1000, tz=UTC),
            candle=candle,
            is_closed_bar=bool(kline["x"]),
        )

    def detect_closed_bar_event(
        self,
        *,
        payload: dict[str, object],
        instrument_id: str,
    ) -> Candle | None:
        """Return a canonical closed candle when the websocket event marks bar close."""

        message = self.normalize_kline_stream_message(payload=payload, instrument_id=instrument_id)
        if not message.is_closed_bar:
            return None
        return message.candle

    def build_bar_slice_from_closed_candles(
        self,
        *,
        instrument_id: str,
        timeframe: str,
        candles: Sequence[Candle],
        limit: int = 2,
    ) -> BarSlice:
        """Build a runtime bar slice from normalized closed candles only."""

        closed = tuple(candle for candle in candles if candle.is_closed)
        if len(closed) < limit:
            raise ValueError(f"insufficient closed candles for timeframe {timeframe}")
        selected = closed[-limit:]
        return BarSlice(
            instrument_id=instrument_id,
            timeframe=timeframe,
            end_time=selected[-1].close_time,
            candles=selected,
        )

    def classify_error(self, message: str) -> BinanceClientError:
        """Classify a market-data error into a normalized category hook."""

        http_status = None
        if "429" in message:
            http_status = 429
        elif "401" in message:
            http_status = 401
        elif "403" in message:
            http_status = 403
        return classify_binance_http_error(
            http_status=http_status,
            json_code=None,
            message=message,
            headers=None,
        )

    def to_venue_symbol(self, instrument_id: str) -> str:
        """Map canonical instrument id to Binance symbol."""

        for mapping in self.symbol_mappings:
            if mapping.instrument_id == instrument_id:
                return mapping.venue_symbol
        return instrument_id.replace("-", "")

    def build_report_only_market_context(
        self,
        *,
        instrument_id: str,
        execution_timeframe: str,
        context_timeframe: str,
        execution_klines: Sequence[Sequence[object]],
        context_klines: Sequence[Sequence[object]],
        reference_time: datetime | None = None,
        execution_limit: int = 2,
        context_limit: int = 2,
    ) -> BinanceReportOnlyMarketContext:
        """Build closed 4h/1d bar inputs from Binance kline payloads.

        This parses the real Binance kline row shape but keeps transport details
        outside the report-only runtime path.
        """

        effective_reference_time = reference_time or datetime.now(UTC)
        execution_bar_slice = self._build_closed_bar_slice(
            instrument_id=instrument_id,
            timeframe=execution_timeframe,
            klines=execution_klines,
            reference_time=effective_reference_time,
            limit=execution_limit,
        )
        context_bar_slice = self._build_closed_bar_slice(
            instrument_id=instrument_id,
            timeframe=context_timeframe,
            klines=context_klines,
            reference_time=effective_reference_time,
            limit=context_limit,
        )
        return BinanceReportOnlyMarketContext(
            execution_bar_slice=execution_bar_slice,
            context_bar_slice=context_bar_slice,
        )

    def _build_closed_bar_slice(
        self,
        *,
        instrument_id: str,
        timeframe: str,
        klines: Sequence[Sequence[object]],
        reference_time: datetime,
        limit: int,
    ) -> BarSlice:
        candles = self._parse_klines(
            instrument_id=instrument_id,
            timeframe=timeframe,
            klines=klines,
            reference_time=reference_time,
        )
        closed_candles = tuple(candle for candle in candles if candle.is_closed)
        if len(closed_candles) < limit:
            raise ValueError(f"insufficient closed candles for timeframe {timeframe}")
        selected = closed_candles[-limit:]
        return BarSlice(
            instrument_id=instrument_id,
            timeframe=timeframe,
            end_time=selected[-1].close_time,
            candles=selected,
        )

    def _parse_klines(
        self,
        *,
        instrument_id: str,
        timeframe: str,
        klines: Sequence[Sequence[object]],
        reference_time: datetime,
    ) -> tuple[Candle, ...]:
        parsed: list[Candle] = []
        reference_ms = int(reference_time.timestamp() * 1000)
        for row in klines:
            if len(row) < 9:
                raise ValueError("binance kline row must contain at least 9 fields")
            open_time_ms = int(row[0])
            close_time_ms = int(row[6])
            parsed.append(
                Candle(
                    instrument_id=instrument_id,
                    timeframe=timeframe,
                    open_time=datetime.fromtimestamp(open_time_ms / 1000, tz=UTC),
                    close_time=datetime.fromtimestamp(close_time_ms / 1000, tz=UTC),
                    open=Decimal(str(row[1])),
                    high=Decimal(str(row[2])),
                    low=Decimal(str(row[3])),
                    close=Decimal(str(row[4])),
                    volume=Decimal(str(row[5])),
                    quote_volume=Decimal(str(row[7])),
                    trade_count=int(row[8]),
                    is_closed=close_time_ms < reference_ms,
                )
            )
        return tuple(parsed)


@dataclass(frozen=True)
class BinancePublicWebSocketClient:
    """Public websocket market-data controller for candle-close driven decisions.

    Transport non-goals for now:
    - no real network connection management in tests
    - no private account/order event handling
    """

    config: BinanceAdapterConfig
    market_data_client: BinanceMarketDataClient
    heartbeat_timeout: timedelta = timedelta(seconds=60)
    session_rollover: timedelta = timedelta(hours=23)
    failover_reconnect_attempts: int = 3

    def build_kline_subscribe_message(self, *, instrument_id: str, timeframe: str) -> dict[str, object]:
        """Return the canonical Binance subscribe payload for a public kline stream."""

        venue_symbol = self.market_data_client.to_venue_symbol(instrument_id).lower()
        return {
            "method": "SUBSCRIBE",
            "params": [f"{venue_symbol}@kline_{timeframe}"],
            "id": 1,
        }

    def normalize_public_message(
        self,
        *,
        payload: dict[str, object],
        instrument_id: str,
    ) -> BinancePublicMarketDataEvent:
        """Normalize one public websocket payload into canonical event form."""

        if payload.get("e") == "kline" or (
            isinstance(payload.get("data"), dict) and payload["data"].get("e") == "kline"
        ):
            message = self.market_data_client.normalize_kline_stream_message(
                payload=payload,
                instrument_id=instrument_id,
            )
            return BinancePublicMarketDataEvent(
                event_type="kline",
                venue_symbol=message.venue_symbol,
                timeframe=message.timeframe,
                kline=message,
                alerts=(),
            )
        if payload.get("op") == "pong" or payload.get("result") == "pong":
            return BinancePublicMarketDataEvent(
                event_type="pong",
                health=BinanceMarketDataHealth(
                    state=BinancePublicStreamState.STREAMING,
                    reconnect_attempts=0,
                    failover_active=False,
                ),
            )
        raise ValueError("unsupported public websocket payload")

    def on_disconnect(self, *, reason: str, reconnect_attempts: int, occurred_at: datetime) -> BinanceMarketDataHealth:
        """Return degraded or failover health state after a disconnect."""

        state = (
            BinancePublicStreamState.FAILOVER_REST
            if reconnect_attempts >= self.failover_reconnect_attempts
            else BinancePublicStreamState.DEGRADED
        )
        alerts = (
            "public websocket unavailable; failover to REST polling required"
            if state is BinancePublicStreamState.FAILOVER_REST
            else f"public websocket disconnected: {reason}",
        )
        return BinanceMarketDataHealth(
            state=state,
            reconnect_attempts=reconnect_attempts,
            failover_active=state is BinancePublicStreamState.FAILOVER_REST,
            last_message_at=occurred_at,
            alerts=(alerts,),
        )

    def on_reconnect(self, *, reconnect_attempts: int, occurred_at: datetime) -> BinanceMarketDataHealth:
        """Return streaming state after a reconnect event."""

        return BinanceMarketDataHealth(
            state=BinancePublicStreamState.STREAMING,
            reconnect_attempts=reconnect_attempts,
            failover_active=False,
            last_message_at=occurred_at,
            alerts=("public websocket reconnected",),
        )

    def on_heartbeat(self, *, occurred_at: datetime, last_heartbeat_at: datetime | None = None) -> BinanceMarketDataHealth:
        """Return heartbeat status and degradation when ping/pong is overdue."""

        if last_heartbeat_at is not None and occurred_at - last_heartbeat_at > self.heartbeat_timeout:
            return BinanceMarketDataHealth(
                state=BinancePublicStreamState.DEGRADED,
                reconnect_attempts=0,
                failover_active=False,
                last_heartbeat_at=occurred_at,
                alerts=("public websocket heartbeat overdue",),
            )
        return BinanceMarketDataHealth(
            state=BinancePublicStreamState.STREAMING,
            reconnect_attempts=0,
            failover_active=False,
            last_heartbeat_at=occurred_at,
            alerts=(),
        )

    def check_session_rollover(
        self,
        *,
        session_started_at: datetime,
        occurred_at: datetime,
    ) -> BinanceMarketDataHealth | None:
        """Return rollover status when the session age exceeds the allowed window."""

        if occurred_at - session_started_at < self.session_rollover:
            return None
        return BinanceMarketDataHealth(
            state=BinancePublicStreamState.SESSION_ROLLOVER,
            reconnect_attempts=0,
            failover_active=False,
            last_message_at=occurred_at,
            alerts=("public websocket session rollover required",),
        )
