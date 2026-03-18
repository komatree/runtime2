from __future__ import annotations

import importlib.util
import json
from argparse import Namespace
from io import BytesIO
from pathlib import Path
import sys
from urllib.error import HTTPError

import pytest


def _load_module():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "run_testnet_event_action_driver.py"
    spec = importlib.util.spec_from_file_location("run_testnet_event_action_driver", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeApi:
    def __init__(self, module) -> None:
        self._module = module

    def symbol_rules(self, symbol: str):
        return self._module.SymbolRules(
            symbol=symbol,
            tick_size=self._module.Decimal("0.10"),
            step_size=self._module.Decimal("0.001"),
            min_qty=self._module.Decimal("0.001"),
            min_notional=self._module.Decimal("5"),
        )

    def last_price(self, symbol: str):
        return self._module.Decimal("100.00")

    def place_limit_order(self, *, symbol: str, side: str, quantity, price, client_order_id: str):
        return (
            {
                "symbol": symbol,
                "orderId": 12345,
                "clientOrderId": client_order_id,
                "price": str(price),
                "origQty": str(quantity),
            },
            200,
        )

    def cancel_order(self, *, symbol: str, order_id: str, client_order_id: str):
        return (
            {
                "symbol": symbol,
                "orderId": order_id,
                "clientOrderId": client_order_id,
                "status": "CANCELED",
            },
            200,
        )

    def place_market_order(self, *, symbol: str, side: str, quantity, client_order_id: str):
        return (
            {
                "symbol": symbol,
                "orderId": 23456,
                "clientOrderId": client_order_id,
                "origQty": str(quantity),
                "status": "FILLED",
            },
            200,
        )


def test_validate_testnet_only_rejects_non_testnet_profile() -> None:
    module = _load_module()
    config = module.BinanceAdapterConfig(
        rest_base_url="https://api.binance.com",
        websocket_base_url="wss://stream.binance.com:9443",
        api_key="test-key",
        api_secret="test-secret",
        endpoint_profile_name="binance_spot_prod",
    )

    with pytest.raises(ValueError):
        module._validate_testnet_only(config)


def test_build_client_order_id_is_binance_safe_and_short() -> None:
    module = _load_module()

    value = module._build_client_order_id(
        run_id="binance-testnet-active-private-driver-20260315-a1",
        action_suffix="c",
    )

    assert len(value) <= 36
    assert value.endswith("-c")
    assert value.replace("-", "").replace("_", "").isalnum()


def test_build_client_order_id_sanitizes_illegal_characters() -> None:
    module = _load_module()

    value = module._build_client_order_id(
        run_id="driver run/with:bad chars?",
        action_suffix="f",
    )

    assert len(value) <= 36
    assert value.endswith("-f")
    assert "/" not in value
    assert ":" not in value
    assert "?" not in value
    assert value.replace("-", "").replace("_", "").isalnum()


def test_run_action_driver_writes_events_and_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    monkeypatch.setenv("BINANCE_API_KEY", "A" * 40)
    monkeypatch.setenv("BINANCE_API_SECRET", "B" * 40)
    config_path = tmp_path / "runtime2_restricted_live_testnet.toml"
    config_path.write_text(
        """
[binance]
endpoint_profile_name = "binance_spot_testnet"
rest_base_url = "https://testnet.binance.vision"
websocket_base_url = "wss://stream.testnet.binance.vision"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    args = Namespace(
        run_id="driver-test",
        config=config_path,
        symbol="BTCUSDT",
        qty="0.010",
        reports_dir=tmp_path / "reports",
        enable_fill_attempt=True,
    )

    exit_code = module.run_action_driver(args, api=_FakeApi(module))

    assert exit_code == 0
    action_dir = tmp_path / "reports" / "event_exercises" / "driver-test" / "action_driver"
    events_path = action_dir / "action_driver_events.jsonl"
    summary_path = action_dir / "action_driver_summary.md"
    assert events_path.exists()
    assert summary_path.exists()

    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    assert [event["action_type"] for event in events] == [
        "place_resting_create_order",
        "cancel_resting_order",
        "place_fill_attempt_order",
    ]
    assert events[0]["client_order_id"].endswith("-c")
    assert events[2]["client_order_id"].endswith("-f")
    assert all(len(event["client_order_id"]) <= 36 for event in events if event["client_order_id"])
    assert all(event["exchange_response_class"] == "success" for event in events)
    summary = summary_path.read_text(encoding="utf-8")
    assert "masked_api_key" in summary
    assert "place_resting_create_order" in summary
    assert "cancel_resting_order" in summary
    assert "place_fill_attempt_order" in summary
    result = json.loads((action_dir / "action_driver_result.json").read_text(encoding="utf-8"))
    assert result["window_outcome"] == module.SUCCESS
    assert result["mandatory_success"] is True
    assert result["create_leg_success"] is True
    assert result["cancel_leg_success"] is True
    assert result["fill_leg_success"] is True


class _PartialSuccessApi(_FakeApi):
    def place_limit_order(self, *, symbol: str, side: str, quantity, price, client_order_id: str):
        return (
            {"code": -1013, "msg": "Filter failure: PERCENT_PRICE_BY_SIDE"},
            400,
        )


class _FatalFailureApi(_FakeApi):
    def place_limit_order(self, *, symbol: str, side: str, quantity, price, client_order_id: str):
        raise RuntimeError("transport exploded")


def test_run_action_driver_emits_partial_success_nonblocking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    monkeypatch.setenv("BINANCE_API_KEY", "A" * 40)
    monkeypatch.setenv("BINANCE_API_SECRET", "B" * 40)
    config_path = tmp_path / "runtime2_restricted_live_testnet.toml"
    config_path.write_text(
        """
[binance]
endpoint_profile_name = "binance_spot_testnet"
rest_base_url = "https://testnet.binance.vision"
websocket_base_url = "wss://stream.testnet.binance.vision"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    args = Namespace(
        run_id="driver-partial",
        config=config_path,
        symbol="BTCUSDT",
        qty="0.010",
        reports_dir=tmp_path / "reports",
        enable_fill_attempt=True,
    )

    exit_code = module.run_action_driver(args, api=_PartialSuccessApi(module))

    assert exit_code == 0
    result = json.loads(
        (tmp_path / "reports" / "event_exercises" / "driver-partial" / "action_driver" / "action_driver_result.json").read_text(
            encoding="utf-8"
        )
    )
    assert result["window_outcome"] == module.PARTIAL_SUCCESS_NONBLOCKING
    assert result["mandatory_success"] is False
    assert result["create_leg_success"] is False
    assert result["cancel_leg_success"] is False
    assert result["fill_leg_success"] is True


def test_main_emits_fatal_failure_result_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    monkeypatch.setenv("BINANCE_API_KEY", "A" * 40)
    monkeypatch.setenv("BINANCE_API_SECRET", "B" * 40)
    config_path = tmp_path / "runtime2_restricted_live_testnet.toml"
    config_path.write_text(
        """
[binance]
endpoint_profile_name = "binance_spot_testnet"
rest_base_url = "https://testnet.binance.vision"
websocket_base_url = "wss://stream.testnet.binance.vision"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "BinanceSpotTestnetActionApi", lambda config: _FatalFailureApi(module))

    with pytest.raises(RuntimeError):
        module.main(
            [
                "--run-id",
                "driver-fatal",
                "--config",
                str(config_path),
                "--symbol",
                "BTCUSDT",
                "--qty",
                "0.010",
                "--reports-dir",
                str(tmp_path / "reports"),
                "--enable-fill-attempt",
            ]
        )

    result = json.loads(
        (tmp_path / "reports" / "event_exercises" / "driver-fatal" / "action_driver" / "action_driver_result.json").read_text(
            encoding="utf-8"
        )
    )
    assert result["window_outcome"] == module.FATAL_FAILURE
    assert result["failure_reasons"] == ["transport exploded"]


def test_request_json_captures_http_error_body_as_binance_payload() -> None:
    module = _load_module()
    request = module.Request("https://testnet.binance.vision/api/v3/order", method="POST")

    def _raise_http_error(req):
        raise HTTPError(
            url=req.full_url,
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=BytesIO(b'{"code":-1013,"msg":"Filter failure: LOT_SIZE"}'),
        )

    payload, http_status = module._request_json(request=request, urlopen_fn=_raise_http_error)
    success, response_class, detail = module._classify_response(payload, http_status)

    assert http_status == 400
    assert payload == {"code": -1013, "msg": "Filter failure: LOT_SIZE"}
    assert success is False
    assert response_class == "failure"
    assert detail == "binance error -1013: Filter failure: LOT_SIZE"
