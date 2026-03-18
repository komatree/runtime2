from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_module():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "verify_binance_signed_paths_testnet.py"
    spec = importlib.util.spec_from_file_location("verify_binance_signed_paths_testnet", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_local_rest_capture_verifies_encoded_query_before_hmac() -> None:
    module = _load_module()
    config = module.BinanceAdapterConfig(
        rest_base_url="https://testnet.binance.vision",
        websocket_base_url="wss://stream.testnet.binance.vision",
        api_key="test-key",
        api_secret="test-secret",
        endpoint_profile_name="binance_spot_testnet",
    )

    result = module._rest_local_capture(config)

    assert result.status == "verified on current local capture"
    assert result.evidence["contains_timestamp"] is True
    assert result.evidence["contains_recv_window"] is True
    assert result.evidence["contains_signature"] is True
    assert result.evidence["signature_matches_expected_hmac"] is True
    assert "origClientOrderId=runtime2+verify%2Fspace%2Bplus%3Atest" in result.evidence["encoded_query_before_signature"]


def test_local_ws_capture_verifies_signed_subscription_payload() -> None:
    module = _load_module()
    config = module.BinanceAdapterConfig(
        rest_base_url="https://testnet.binance.vision",
        websocket_base_url="wss://stream.testnet.binance.vision",
        api_key="test-key",
        api_secret="test-secret",
        endpoint_profile_name="binance_spot_testnet",
    )

    result = module._ws_local_capture(config)

    assert result.status == "verified on current local capture"
    assert result.evidence["request_method"] == "userDataStream.subscribe.signature"
    assert result.evidence["contains_api_key"] is True
    assert result.evidence["contains_timestamp"] is True
    assert result.evidence["contains_recv_window"] is True
    assert result.evidence["contains_signature"] is True
    assert result.evidence["signature_matches_expected_hmac"] is True


def test_recv_window_timestamp_result_is_partial_without_live_proof() -> None:
    module = _load_module()
    rest_result = module.VerificationResult(
        name="rest",
        path_type="signed_rest_order_lookup",
        status="not verified",
        verified_live=False,
        detail="not attempted",
    )
    ws_result = module.VerificationResult(
        name="ws",
        path_type="ws_api_user_data_subscription",
        status="not verified",
        verified_live=False,
        detail="not attempted",
    )

    result = module._recv_window_timestamp_assumption_result(rest_result, ws_result)

    assert result.status == "partially verified"
    assert result.verified_live is False


def test_live_rest_verification_does_not_mark_dns_failure_as_verified(monkeypatch) -> None:
    module = _load_module()
    config = module.BinanceAdapterConfig(
        rest_base_url="https://testnet.binance.vision",
        websocket_base_url="wss://stream.testnet.binance.vision",
        api_key="test-key",
        api_secret="test-secret",
        endpoint_profile_name="binance_spot_testnet",
    )

    class _FakeTransport:
        def __init__(self, **kwargs) -> None:
            self._health = type(
                "_Health",
                (),
                {
                    "state": type("_State", (), {"value": "failed"})(),
                    "alert": "[Errno -3] Temporary failure in name resolution",
                },
            )

        def lookup_by_client_order_id(self, *, client_order_id: str):
            return type(
                "_LookupResult",
                (),
                {
                    "found": False,
                    "alert": "[Errno -3] Temporary failure in name resolution",
                },
            )

        def last_health(self):
            return self._health

    monkeypatch.setattr(
        module,
        "_create_live_rest_probe_order",
        lambda config: module._RestProbeTarget(
            symbol="BTCUSDT",
            quantity="0.01",
            client_order_id="probe-client",
            exchange_order_id="probe-order",
            create_http_status=200,
            create_order_status="FILLED",
        ),
    )
    monkeypatch.setattr(module, "BinanceSignedRestOrderStatusTransport", _FakeTransport)

    result = module._live_rest_verification(config)

    assert result.status == "not verified"
    assert result.verified_live is False
    assert "environment/transport error" in result.detail


def test_live_rest_verification_marks_real_lookup_success_as_verified(monkeypatch) -> None:
    module = _load_module()
    config = module.BinanceAdapterConfig(
        rest_base_url="https://testnet.binance.vision",
        websocket_base_url="wss://stream.testnet.binance.vision",
        api_key="test-key",
        api_secret="test-secret",
        endpoint_profile_name="binance_spot_testnet",
    )

    class _FakeTransport:
        def __init__(self, **kwargs) -> None:
            self._health = type(
                "_Health",
                (),
                {
                    "state": type("_State", (), {"value": "success"})(),
                    "alert": None,
                },
            )

        def lookup_by_client_order_id(self, *, client_order_id: str):
            return type(
                "_LookupResult",
                (),
                {
                    "found": True,
                    "alert": None,
                },
            )

        def last_health(self):
            return self._health

    monkeypatch.setattr(
        module,
        "_create_live_rest_probe_order",
        lambda config: module._RestProbeTarget(
            symbol="BTCUSDT",
            quantity="0.01",
            client_order_id="probe-client",
            exchange_order_id="probe-order",
            create_http_status=200,
            create_order_status="FILLED",
        ),
    )
    monkeypatch.setattr(module, "BinanceSignedRestOrderStatusTransport", _FakeTransport)

    result = module._live_rest_verification(config)

    assert result.status == "verified on current Spot testnet"
    assert result.verified_live is True
    assert result.evidence["probe_order_source"] == "harness_created_market_order"
    assert result.evidence["probe_client_order_id"] == "probe-client"
    assert result.evidence["probe_exchange_order_id"] == "probe-order"
