#!/usr/bin/env python3
"""Read-only local sanity checks for Binance Spot testnet credentials.

This helper does not contact Binance and does not print raw secrets.
It only checks whether the currently injected environment variables look
plausible for Spot testnet rehearsal use.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

API_KEY_PATTERN = re.compile(r"^[A-Za-z0-9]{36,64}$")


def _fingerprint(value: str) -> str:
    if not value:
        return "<missing>"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _load_binance_config(config_path: Path) -> dict[str, str]:
    payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    binance = payload["binance"]
    return {
        "endpoint_profile_name": str(binance["endpoint_profile_name"]),
        "rest_base_url": str(binance["rest_base_url"]),
        "websocket_base_url": str(binance["websocket_base_url"]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Binance Spot testnet credential sanity checks")
    parser.add_argument(
        "--config",
        default="configs/runtime2_restricted_live_testnet.toml",
        help="runtime2 Binance Spot testnet config path",
    )
    args = parser.parse_args(argv)

    config_path = (ROOT / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    binance = _load_binance_config(config_path)
    key = os.environ.get("BINANCE_API_KEY", "")
    secret = os.environ.get("BINANCE_API_SECRET", "")

    key_trimmed = key.strip()
    secret_trimmed = secret.strip()
    key_has_ws = key != key_trimmed
    secret_has_ws = secret != secret_trimmed
    key_has_newline = "\n" in key or "\r" in key
    secret_has_newline = "\n" in secret or "\r" in secret
    key_shape_ok = bool(API_KEY_PATTERN.fullmatch(key))
    key_secret_equal = bool(key) and key == secret
    placeholder_like = key in {"...", "dummy", "test", "placeholder"} or secret in {"...", "dummy", "test", "placeholder"}
    testnet_profile_ok = binance["endpoint_profile_name"] == "binance_spot_testnet"
    testnet_hosts_ok = "testnet.binance.vision" in binance["rest_base_url"] and "testnet.binance.vision" in binance["websocket_base_url"]

    print(f"config_path: {config_path}")
    print(f"endpoint_profile_name: {binance['endpoint_profile_name']}")
    print(f"rest_base_url: {binance['rest_base_url']}")
    print(f"websocket_base_url: {binance['websocket_base_url']}")
    print(f"testnet_profile_ok: {testnet_profile_ok}")
    print(f"testnet_hosts_ok: {testnet_hosts_ok}")
    print(f"api_key_present: {bool(key)}")
    print(f"api_secret_present: {bool(secret)}")
    print(f"api_key_length: {len(key)}")
    print(f"api_secret_length: {len(secret)}")
    print(f"api_key_shape_ok: {key_shape_ok}")
    print(f"api_key_has_leading_or_trailing_whitespace: {key_has_ws}")
    print(f"api_secret_has_leading_or_trailing_whitespace: {secret_has_ws}")
    print(f"api_key_has_newline: {key_has_newline}")
    print(f"api_secret_has_newline: {secret_has_newline}")
    print(f"api_key_equals_secret: {key_secret_equal}")
    print(f"placeholder_like_value_detected: {placeholder_like}")
    print(f"api_key_fingerprint12: {_fingerprint(key)}")
    print(f"api_secret_fingerprint12: {_fingerprint(secret)}")

    problems: list[str] = []
    if not testnet_profile_ok or not testnet_hosts_ok:
        problems.append("config does not point cleanly to Binance Spot testnet")
    if not key or not secret:
        problems.append("credential env vars are missing")
    if placeholder_like:
        problems.append("placeholder-like credential value detected")
    if key_secret_equal:
        problems.append("api key and secret are identical, which is not expected")
    if key_has_ws or secret_has_ws:
        problems.append("credential value has leading/trailing whitespace")
    if key_has_newline or secret_has_newline:
        problems.append("credential value contains a newline")
    if key and not key_shape_ok:
        problems.append("api key does not match the Binance WS-API legal character shape")

    if problems:
        print("status: blocked")
        print("problems:")
        for problem in problems:
            print(f"- {problem}")
        return 1

    print("status: locally plausible")
    print("note: this does not prove the credentials are valid on Binance; it only checks local injection and obvious shape issues")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
