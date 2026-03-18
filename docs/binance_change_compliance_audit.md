# Binance Change Compliance Audit

## Scope

This audit checks `runtime2` against the currently relevant Binance Spot API changes and current 2026-direction Spot API expectations.

Primary external references:
- Binance Spot API changelog: <https://github.com/binance/binance-spot-api-docs/blob/master/CHANGELOG.md>
- Binance Spot WS-API user data stream requests: <https://developers.binance.com/docs/binance-spot-api-docs/websocket-api/user-data-stream-requests>
- Binance Spot request security: <https://developers.binance.com/docs/binance-spot-api-docs/rest-api/request-security>
- Binance Spot user data stream event docs: <https://developers.binance.com/docs/binance-spot-api-docs/user-data-stream>
- Binance Spot filters: <https://developers.binance.com/docs/binance-spot-api-docs/filters>

## Summary

`runtime2` is already aligned with the biggest Binance Spot private-stream migration: it no longer depends on the deprecated REST listenKey bootstrap for the restricted-live private stream. The private bootstrap path now uses authenticated WS-API subscription.

The remaining gaps are not broad architectural mismatches. They are narrower verification gaps:
- explicit proof that all signed paths remain correct under Binance's current percent-encode-before-HMAC expectation
- explicit tolerance tests for `executionReport` fields such as `eR` / expiry reason variants
- explicit guards or tests for future iceberg behavior changes
- real active private-event evidence, not only idle-stream soak evidence

## Item-by-Item Classification

### 1. v1 endpoint retirement

Status: `handled and verified`

Evidence:
- Repo-wide scan found no `/api/v1` usage in `app/`, `scripts/`, `configs/`, `docs/`, or `tests/`.
- Current signed REST lookup path uses `/api/v3/order` in [`app/exchanges/binance/order_client.py`](/home/terratunes/code/trading/runtime2/app/exchanges/binance/order_client.py).
- Current private bootstrap path uses Spot WS-API in [`app/exchanges/binance/private_transport.py`](/home/terratunes/code/trading/runtime2/app/exchanges/binance/private_transport.py).

Residual gap:
- no dedicated regression test that fails if `/api/v1` usage is reintroduced later

### 2. Deprecated `listenKey` / `userDataStream.start-ping-stop` removal

Status: `handled and verified`

Evidence:
- No active `userDataStream.start`, `userDataStream.ping`, or `userDataStream.stop` calls were found anywhere in the repo.
- The private bootstrap transport explicitly documents and replaces the old REST listenKey assumption in [`app/exchanges/binance/private_transport.py`](/home/terratunes/code/trading/runtime2/app/exchanges/binance/private_transport.py).
- The current bootstrap request uses `userDataStream.subscribe.signature` in:
  - [`app/exchanges/binance/private_transport.py`](/home/terratunes/code/trading/runtime2/app/exchanges/binance/private_transport.py)
  - [`app/exchanges/binance/private_stream_client.py`](/home/terratunes/code/trading/runtime2/app/exchanges/binance/private_stream_client.py)
- Transport tests cover the authenticated subscription bootstrap and event ingestion shape in:
  - [`tests/exchanges/test_binance_transport_integration.py`](/home/terratunes/code/trading/runtime2/tests/exchanges/test_binance_transport_integration.py)
  - [`tests/exchanges/test_binance_private_stream_lifecycle.py`](/home/terratunes/code/trading/runtime2/tests/exchanges/test_binance_private_stream_lifecycle.py)

Important nuance:
- `listenKeyExpired` still appears in translator/tests because it is treated as an incoming termination event type, not as a bootstrap mechanism.
- `listen_key_refresh.jsonl` remains as an artifact filename in rehearsal monitoring. That is naming drift, not deprecated API use.

### 3. WS-API `userDataStream` subscription alignment

Status: `handled and verified`

Evidence:
- Private bootstrap now opens the authenticated WS-API connection and calls `userDataStream.subscribe.signature` in [`app/exchanges/binance/private_transport.py`](/home/terratunes/code/trading/runtime2/app/exchanges/binance/private_transport.py).
- Endpoint-profile isolation supports both prod and Spot testnet in [`app/exchanges/binance/endpoint_profiles.py`](/home/terratunes/code/trading/runtime2/app/exchanges/binance/endpoint_profiles.py).
- Testnet rehearsal config is separated in [`configs/runtime2_restricted_live_testnet.toml`](/home/terratunes/code/trading/runtime2/configs/runtime2_restricted_live_testnet.toml).
- Reconnect and rollover behavior is covered in:
  - [`tests/exchanges/test_binance_private_stream_lifecycle.py`](/home/terratunes/code/trading/runtime2/tests/exchanges/test_binance_private_stream_lifecycle.py)
  - [`tests/exchanges/test_binance_restricted_live_transport.py`](/home/terratunes/code/trading/runtime2/tests/exchanges/test_binance_restricted_live_transport.py)

Residual gap:
- long-running real WS-API durability is still an operational evidence problem, not a protocol-alignment problem

### 4. `executionReport` `expiryReason` / `eR` tolerance

Status: `handled but not yet verified`

Evidence:
- The canonical private payload translator maps required order/fill fields explicitly and ignores unrelated extra fields by default in [`app/exchanges/binance/private_payload_translator.py`](/home/terratunes/code/trading/runtime2/app/exchanges/binance/private_payload_translator.py).
- That means extra Binance keys such as `eR` should not currently break translation unless Binance changes required-field semantics.

Why this is not fully verified:
- no test currently injects `executionReport` payloads containing `eR` or explicit expiry-reason variants
- no operator-visible normalization policy currently records expiry-reason semantics separately

Needed explicit coverage:
- one translator test with `eR` present on a valid `executionReport`
- one translator test with an expiry-related terminal event and extra expiry-reason metadata

### 5. Percent-encode-before-HMAC signing

Status: `handled but not yet verified`

Evidence:
- Signed REST order lookup uses `urllib.parse.urlencode(...)` before HMAC in [`app/exchanges/binance/order_client.py`](/home/terratunes/code/trading/runtime2/app/exchanges/binance/order_client.py).
- Signed REST lookup transport is already exercised in [`tests/exchanges/test_binance_transport_integration.py`](/home/terratunes/code/trading/runtime2/tests/exchanges/test_binance_transport_integration.py).

Why this is not fully verified:
- there is no explicit test using special-character signed parameters to prove encoding and signature behavior on current Spot testnet
- the WS-API subscription signing path in [`app/exchanges/binance/private_transport.py`](/home/terratunes/code/trading/runtime2/app/exchanges/binance/private_transport.py) builds the signing string manually from simple parameters (`apiKey`, `recvWindow`, `timestamp`)
- current WS-API subscription params are simple enough that this probably works in practice, but the repo does not yet have explicit test evidence for current Binance signing expectations or `-1022 INVALID_SIGNATURE` prevention

Needed explicit coverage:
- live testnet verification of signed REST lookup
- live testnet verification of signed WS-API `userDataStream.subscribe.signature`
- unit/integration coverage for special-character query values where Binance allows them

### 6. `ICEBERG_PARTS = 100` implications

Status: `not yet handled`

Evidence:
- no iceberg-order validation or execution path was found in the current runtime2 Binance adapter
- no `ICEBERG_PARTS` logic or tests exist in `app/` or `tests/`

Why this is currently acceptable but incomplete:
- `runtime2` restricted-live remains rehearsal-only and still does not open unrestricted live order submission
- so the changed Binance limit is not currently impacting an active production path

What still needs to happen:
- if iceberg support is ever enabled, add explicit order validation against current Binance filter limits
- add test coverage for rejection/fail-closed handling around iceberg-part limits

### 7. Active private-event evidence gaps

Status: `handled but not yet verified`

Evidence:
- runtime2 has canonical translation, reconciliation, mutation gating, and soak/failure-injection scaffolding
- the private-event path is well covered by unit/integration tests:
  - [`tests/exchanges/test_binance_private_payload_translation.py`](/home/terratunes/code/trading/runtime2/tests/exchanges/test_binance_private_payload_translation.py)
  - [`tests/exchanges/test_binance_transport_integration.py`](/home/terratunes/code/trading/runtime2/tests/exchanges/test_binance_transport_integration.py)
  - [`tests/runtime/test_restricted_live_failure_injection.py`](/home/terratunes/code/trading/runtime2/tests/runtime/test_restricted_live_failure_injection.py)

Why this is still only partial:
- reviewed real soak evidence so far has been idle-stream durability evidence, not active private-event evidence
- the reviewed soak runs did not exercise:
  - live order/account private payload flow
  - reconciliation recovery under real private event loss
  - mutation gate behavior under real private event arrival

Needed explicit verification:
- at least one real testnet rehearsal session with actual private order/account events
- artifact review showing translation, gate decisions, and recovery behavior under real active private flow

## Recommended Next Explicit Tests

1. Add translator coverage for `executionReport` with `eR` / expiry-reason fields.
2. Add signed-path verification coverage for special-character-safe signing and current Spot testnet behavior.
3. Add one active private-event rehearsal where testnet order/account events are intentionally generated and preserved in soak artifacts.

## Conservative Conclusion

The important 2026 Binance Spot direction changes are already reflected in runtime2 where they matter most:
- no deprecated REST listenKey bootstrap in the private stream path
- no `userDataStream.start/ping/stop` usage
- current WS-API subscription model is implemented

The remaining work is mostly explicit verification and evidence collection, not a major protocol migration.
