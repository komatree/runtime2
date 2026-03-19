"""Real Binance private-stream transport implementations inside adapter boundaries."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import socket
import ssl
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from typing import Protocol
from typing import Mapping
from urllib.parse import urlparse
from urllib.request import Request
from urllib.request import urlopen

from .endpoint_profiles import validate_endpoint_profile
from .models import BinanceAdapterConfig
from .models import BinancePrivateStreamSubscription
from .throttling import BinanceRequestWeightTracker


class WebSocketConnection(Protocol):
    """Minimal websocket connection boundary used by the private transport."""

    def recv_text(self) -> str:
        """Return the next text frame payload."""

    def send_text(self, text: str) -> None:
        """Send one text frame."""

    def close(self) -> None:
        """Close the websocket connection."""


class WebSocketConnectionFactory(Protocol):
    """Factory for authenticated private websocket connections."""

    def connect(self, *, url: str, headers: dict[str, str] | None = None) -> WebSocketConnection:
        """Open a websocket connection and return the connection object."""


class BinancePrivateStreamReadTimeout(TimeoutError):
    """Raised when a private-stream read waits too long without a new payload."""


class StdlibWebSocketConnection:
    """Minimal stdlib websocket client for Binance-style text streams.

    This client is intentionally narrow:
    - text frames only for normal message flow
    - ping/pong handled internally
    - no fragmentation support beyond simple unfragmented frames
    """

    def __init__(
        self,
        *,
        url: str,
        headers: dict[str, str] | None = None,
        read_timeout_seconds: float = 5.0,
    ) -> None:
        self._url = url
        self._headers = headers or {}
        self._read_timeout_seconds = read_timeout_seconds
        self._sock = self._connect()

    def recv_text(self) -> str:
        while True:
            opcode, payload = self._read_frame()
            if opcode == 0x1:
                return payload.decode("utf-8")
            if opcode == 0x9:
                self._send_frame(0xA, payload)
                continue
            if opcode == 0x8:
                raise ConnectionError("websocket closed by remote peer")
            if opcode == 0xA:
                continue
            raise ConnectionError(f"unsupported websocket opcode: {opcode}")

    def send_text(self, text: str) -> None:
        self._send_frame(0x1, text.encode("utf-8"))

    def close(self) -> None:
        try:
            self._send_frame(0x8, b"")
        except OSError:
            pass
        self._sock.close()

    def _connect(self):
        parsed = urlparse(self._url)
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        raw_sock = socket.create_connection((host, port))
        if parsed.scheme == "wss":
            context = ssl.create_default_context()
            sock = context.wrap_socket(raw_sock, server_hostname=host)
        else:
            sock = raw_sock
        sock.settimeout(self._read_timeout_seconds)

        key = base64.b64encode(os.urandom(16)).decode("ascii")
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        request_headers = {
            "Host": host,
            "Upgrade": "websocket",
            "Connection": "Upgrade",
            "Sec-WebSocket-Version": "13",
            "Sec-WebSocket-Key": key,
            **self._headers,
        }
        header_blob = "".join(f"{name}: {value}\r\n" for name, value in request_headers.items())
        request = f"GET {path} HTTP/1.1\r\n{header_blob}\r\n".encode("utf-8")
        sock.sendall(request)

        response = self._read_http_response(sock)
        if "101" not in response.splitlines()[0]:
            raise ConnectionError(f"websocket handshake failed: {response.splitlines()[0]}")
        accept_value = ""
        for line in response.split("\r\n")[1:]:
            if line.lower().startswith("sec-websocket-accept:"):
                accept_value = line.split(":", 1)[1].strip()
                break
        expected_accept = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        ).decode("ascii")
        if accept_value != expected_accept:
            raise ConnectionError("invalid websocket accept response")
        return sock

    def _read_http_response(self, sock) -> str:
        data = bytearray()
        while b"\r\n\r\n" not in data:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError("unexpected EOF during websocket handshake")
            data.extend(chunk)
        return data.decode("utf-8", errors="replace")

    def _read_exact(self, size: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < size:
            chunk = self._sock.recv(size - len(chunks))
            if not chunk:
                raise ConnectionError("unexpected EOF while reading websocket frame")
            chunks.extend(chunk)
        return bytes(chunks)

    def _read_frame(self) -> tuple[int, bytes]:
        first, second = self._read_exact(2)
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            length = int.from_bytes(self._read_exact(2), "big")
        elif length == 127:
            length = int.from_bytes(self._read_exact(8), "big")
        mask = self._read_exact(4) if masked else b""
        payload = self._read_exact(length)
        if masked:
            payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        return opcode, payload

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        first = 0x80 | (opcode & 0x0F)
        mask = os.urandom(4)
        length = len(payload)
        if length < 126:
            header = bytes([first, 0x80 | length])
        elif length < 65536:
            header = bytes([first, 0x80 | 126]) + length.to_bytes(2, "big")
        else:
            header = bytes([first, 0x80 | 127]) + length.to_bytes(8, "big")
        masked_payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        self._sock.sendall(header + mask + masked_payload)


@dataclass(frozen=True)
class StdlibWebSocketConnectionFactory:
    """Default websocket factory using the stdlib websocket client."""

    read_timeout_seconds: float = 5.0

    def connect(self, *, url: str, headers: dict[str, str] | None = None) -> WebSocketConnection:
        return StdlibWebSocketConnection(
            url=url,
            headers=headers,
            read_timeout_seconds=self.read_timeout_seconds,
        )


@dataclass
class BinancePrivateUserDataTransport:
    """Authenticated Binance private-stream transport using the Spot WS API.

    The old REST listenKey bootstrap path now returns HTTP 410 Gone on current
    Spot accounts because Binance has moved user-data stream subscription to the
    WebSocket API. This transport bootstraps via an authenticated WS-API
    connection and `userDataStream.subscribe.signature` instead.
    """

    rest_base_url: str
    websocket_base_url: str
    api_key: str
    api_secret: str
    websocket_factory: WebSocketConnectionFactory = StdlibWebSocketConnectionFactory()
    urlopen_fn: object = urlopen
    request_weight_tracker: BinanceRequestWeightTracker | None = None
    endpoint_profile_name: str = "binance_spot_prod"
    recv_window_ms: int = 5000
    session_ttl_seconds: int = 24 * 60 * 60

    def __post_init__(self) -> None:
        validate_endpoint_profile(
            BinanceAdapterConfig(
                rest_base_url=self.rest_base_url,
                websocket_base_url=self.websocket_base_url,
                endpoint_profile_name=self.endpoint_profile_name,
            )
        )
        self._connections: dict[str, WebSocketConnection] = {}
        self._pending_messages: dict[str, list[dict[str, object]]] = {}
        self._subscriptions: dict[str, BinancePrivateStreamSubscription] = {}
        self._next_connection_id = 1
        self._next_request_id = 1

    def open_connection(self, *, account_scope: str) -> str:
        url = self._ws_api_url()
        connection = self.websocket_factory.connect(url=url)
        connection_id = f"private-connection-{self._next_connection_id}"
        self._next_connection_id += 1
        self._connections[connection_id] = connection
        self._pending_messages[connection_id] = []
        return connection_id

    def subscribe(
        self,
        *,
        connection_id: str,
        account_scope: str,
    ) -> BinancePrivateStreamSubscription:
        if connection_id not in self._connections:
            raise KeyError(f"unknown private connection: {connection_id}")
        self._reserve_weight(endpoint="ws-api:userDataStream.subscribe.signature", weight=2)
        request_id = self._next_request_id
        self._next_request_id += 1
        params = self._signed_ws_api_params()
        request = {
            "id": request_id,
            "method": "userDataStream.subscribe.signature",
            "params": params,
        }
        self._connections[connection_id].send_text(json.dumps(request, sort_keys=True))
        response = self._await_response(connection_id=connection_id, request_id=request_id)
        subscription_id = self._extract_subscription_id(response)
        subscription = BinancePrivateStreamSubscription(
            subscription_id=subscription_id,
            stream_key=f"subscription-{subscription_id}",
            bootstrap_method="userDataStream.subscribe.signature",
            expires_at=datetime.now(UTC) + timedelta(seconds=self.session_ttl_seconds),
        )
        self._subscriptions[connection_id] = subscription
        return subscription

    def close_connection(self, *, connection_id: str) -> None:
        connection = self._connections.pop(connection_id, None)
        self._pending_messages.pop(connection_id, None)
        self._subscriptions.pop(connection_id, None)
        if connection is not None:
            connection.close()

    def read_payload(self, *, connection_id: str) -> dict[str, object]:
        if connection_id not in self._connections:
            raise KeyError(f"unknown private connection: {connection_id}")
        queued = self._pending_messages.get(connection_id)
        if queued:
            parsed = queued.pop(0)
        else:
            try:
                raw = self._connections[connection_id].recv_text()
            except socket.timeout as exc:
                raise BinancePrivateStreamReadTimeout("private websocket read timed out") from exc
            except TimeoutError as exc:
                raise BinancePrivateStreamReadTimeout("private websocket read timed out") from exc
            parsed = json.loads(raw)
        normalized = self._normalize_event_payload(parsed)
        if not isinstance(normalized, dict):
            raise ValueError("private websocket payload must decode to an object")
        if "e" not in normalized:
            raise ValueError("private websocket payload missing event type")
        return normalized

    def latest_weight_snapshot(self):
        """Return the latest control-plane request-weight state when configured."""

        if self.request_weight_tracker is None:
            return None
        return self.request_weight_tracker.latest_snapshot()

    def _reserve_weight(self, *, endpoint: str, weight: int) -> None:
        if self.request_weight_tracker is None:
            return
        snapshot = self.request_weight_tracker.consume(
            endpoint=endpoint,
            weight=weight,
            occurred_at=datetime.now(UTC),
        )
        if snapshot.is_throttled:
            raise RuntimeError(snapshot.alert or "request-weight budget exceeded")

    def _observe_weight_headers(self, *, response: object, endpoint: str) -> None:
        if self.request_weight_tracker is None:
            return
        self.request_weight_tracker.observe_response_headers(
            headers=_response_headers(response),
            endpoint=endpoint,
            occurred_at=datetime.now(UTC),
        )

    def _ws_api_url(self) -> str:
        if self.endpoint_profile_name == "binance_spot_prod":
            return "wss://ws-api.binance.com:443/ws-api/v3"
        if self.endpoint_profile_name == "binance_spot_testnet":
            return "wss://ws-api.testnet.binance.vision/ws-api/v3"
        raise ValueError(f"unsupported Binance endpoint profile for WS-API private stream: {self.endpoint_profile_name}")

    def _signed_ws_api_params(self) -> dict[str, object]:
        timestamp = int(datetime.now(UTC).timestamp() * 1000)
        params = {
            "apiKey": self.api_key,
            "recvWindow": self.recv_window_ms,
            "timestamp": timestamp,
        }
        query = "&".join(
            f"{key}={params[key]}"
            for key in sorted(params)
        )
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            **params,
            "signature": signature,
        }

    def _await_response(self, *, connection_id: str, request_id: int) -> dict[str, object]:
        connection = self._connections[connection_id]
        while True:
            raw = connection.recv_text()
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError("private WS-API response must decode to an object")
            if parsed.get("id") == request_id:
                status = parsed.get("status")
                if status not in (None, 200):
                    message = parsed.get("error") or parsed.get("msg") or "private WS-API request failed"
                    raise RuntimeError(f"Binance private WS-API request failed: {message}")
                if "error" in parsed:
                    raise RuntimeError(f"Binance private WS-API request failed: {parsed['error']}")
                return parsed
            self._pending_messages[connection_id].append(parsed)

    def _extract_subscription_id(self, response: dict[str, object]) -> str:
        result = response.get("result")
        if isinstance(result, dict) and result.get("subscriptionId") is not None:
            return str(result["subscriptionId"])
        if response.get("subscriptionId") is not None:
            return str(response["subscriptionId"])
        if result not in (None, "") and not isinstance(result, dict):
            return str(result)
        raise ValueError("private WS-API subscribe response missing subscriptionId")

    def _normalize_event_payload(self, parsed: object) -> dict[str, object]:
        if not isinstance(parsed, dict):
            raise ValueError("private websocket payload must decode to an object")
        if isinstance(parsed.get("event"), dict):
            parsed = parsed["event"]
        elif isinstance(parsed.get("data"), dict):
            parsed = parsed["data"]
        if not isinstance(parsed, dict):
            raise ValueError("private websocket payload must decode to an object")
        if "status" in parsed and parsed.get("e") is None and parsed.get("event") is None:
            raise ValueError("private websocket payload is a control response, not an event")
        return parsed


def _response_headers(response: object) -> Mapping[str, str]:
    headers = getattr(response, "headers", None)
    if headers is None:
        return {}
    if hasattr(headers, "items"):
        return {str(key): str(value) for key, value in headers.items()}
    return {}
