# Binance Signed Path Verification Results

## Scope

This document records the current verification status for the Binance signed paths that `runtime2` depends on.

Primary references:
- [`docs/binance_signed_path_verification_plan.md`](/home/terratunes/code/trading/runtime2/docs/binance_signed_path_verification_plan.md)
- [`scripts/verify_binance_signed_paths_testnet.py`](/home/terratunes/code/trading/runtime2/scripts/verify_binance_signed_paths_testnet.py)

## Current Result Set

Current repository/session status:
- local capture verification: implemented and runnable
- live Spot testnet verification harness: implemented
- latest reviewed standalone live Spot testnet artifact set: checked at `2026-03-15T08:08:59.294173+00:00`

Reviewed live artifacts:
- [`reports/signed_path_verification/latest/signed_path_summary.json`](/home/terratunes/code/trading/runtime2/reports/signed_path_verification/latest/signed_path_summary.json)
- [`reports/signed_path_verification/latest/signed_path_summary.md`](/home/terratunes/code/trading/runtime2/reports/signed_path_verification/latest/signed_path_summary.md)

## Current Classification

| Path | Status | Why |
| --- | --- | --- |
| REST signed request path used for authenticated checks / status lookup | `verified on current Spot testnet` | the latest preserved live artifact shows the harness-created probe order was successfully created and then found through the runtime2 signed REST lookup path |
| WS-API signing path used for `userDataStream.subscribe.signature` | `verified on current Spot testnet` | the latest preserved standalone live artifact shows Spot testnet accepted `userDataStream.subscribe.signature` for the runtime2 path |
| timestamp / recvWindow handling assumptions | `verified on current Spot testnet` | both signed REST and signed WS checks now succeed on Spot testnet with the runtime2 timestamp and `recvWindow` assumptions |
| percent-encoding-before-HMAC behavior | `verified on current local capture` and supported by live pass | local capture verifies the encoded query is signed before HMAC for the REST path, and the latest live pass shows the same signed REST path is accepted on Spot testnet |

## Reviewed Live Evidence

Live harness command used:

```bash
python scripts/verify_binance_signed_paths_testnet.py \
  --config configs/runtime2_restricted_live_testnet.toml \
  --allow-live-testnet \
  --output-dir reports/signed_path_verification/latest
```

Reviewed standalone live results from `2026-03-15T08:08:59.294173+00:00`:
- REST signed lookup: `verified on current Spot testnet`
  - runtime2 created one minimal harness-owned market-order probe on Spot testnet
  - runtime2 then found that same order through the signed REST lookup path
  - probe evidence includes:
    - `probe_order_source: harness_created_market_order`
    - `probe_client_order_id: rt2-rest-probe-1773562139`
    - `probe_exchange_order_id: 17402610`
    - `probe_create_order_status: FILLED`
    - `found: true`
  - conclusion: standalone REST signed lookup is now verified
- WS-API user-data subscription: `verified on current Spot testnet`
  - Spot testnet accepted runtime2 `userDataStream.subscribe.signature`
  - conclusion: WS signed subscription is now verified as a standalone preserved class
- shared timestamp / `recvWindow` assumptions: `verified on current Spot testnet`
  - both signed REST and signed WS paths were accepted live
  - live proof is now sufficient for the shared assumption class

Live-evidence blocker classification:
- no remaining standalone signed-path blocker in the latest preserved artifact set
- not currently indicated as blockers:
  - `timestamp/recvWindow issue`
  - `signature issue`
  - `WS signed subscription acceptance`
  - `REST lookup target semantics`

Conservative interpretation:
- the reviewed live artifact set shows that the harness is functioning and reaching Binance Spot testnet
- the preserved standalone WS signed-subscription class is verified
- the preserved standalone REST signed lookup class is also now verified
- the preserved standalone signed-path baseline is now sufficient to stop being a true gate blocker

## What Is Verified Now

Verified now in-repo:
- runtime2 has a dedicated Spot testnet signed-path verification harness at [`scripts/verify_binance_signed_paths_testnet.py`](/home/terratunes/code/trading/runtime2/scripts/verify_binance_signed_paths_testnet.py)
- the harness reuses the existing adapter transports rather than introducing a second production signing path
- the live REST verification path now creates one minimal testnet market-order target immediately before lookup so the signed REST check can prove lookup acceptance against a valid order target
- the harness verifies locally that:
  - signed REST lookup includes `timestamp`, `recvWindow`, and `signature`
  - the REST query is percent-encoded before HMAC
  - WS-API `userDataStream.subscribe.signature` includes `apiKey`, `timestamp`, `recvWindow`, and `signature`
  - WS-API subscription payload signing matches the expected HMAC over the canonical parameter string

Supporting tests:
- [`tests/scripts/test_verify_binance_signed_paths_testnet.py`](/home/terratunes/code/trading/runtime2/tests/scripts/test_verify_binance_signed_paths_testnet.py)

## What Remains Unverified

Still not fully verified:
- exotic special-character credential safety using every Binance-allowed value family on Spot testnet

## Safe Operator Command

Local-only verification:

```bash
python scripts/verify_binance_signed_paths_testnet.py \
  --config configs/runtime2_restricted_live_testnet.toml \
  --output-dir reports/signed_path_verification/latest
```

Live Spot testnet verification:

```bash
env BINANCE_API_KEY='your_testnet_key' BINANCE_API_SECRET='your_testnet_secret' \
python scripts/verify_binance_signed_paths_testnet.py \
  --config configs/runtime2_restricted_live_testnet.toml \
  --allow-live-testnet \
  --output-dir reports/signed_path_verification/latest
```

Expected artifacts:
- `reports/signed_path_verification/latest/signed_path_summary.json`
- `reports/signed_path_verification/latest/signed_path_summary.md`

For a successful live REST pass after the harness correction, the artifact should show evidence fields similar to:
- `probe_order_source: harness_created_market_order`
- `probe_client_order_id: ...`
- `probe_exchange_order_id: ...`
- `probe_create_order_status: FILLED`
- `found: true`

## Conservative Conclusion

Signed-path confidence is improved because there is now one explicit verification harness using the actual runtime2 adapter signing paths.

Signed-path confidence is now strong enough to count as a preserved standalone evidence class for the current runtime2 paths.

Current verdict:
- REST signed path: `passed`
- WS-API signed subscription path: `passed`
- overall signed-path status: `passed`

Exact current interpretation:
- the latest preserved standalone artifact set verifies both the signed REST lookup path and the WS signed subscription path
- the REST pass now uses a minimal harness-created testnet order target and a subsequent successful signed lookup
- the shared timestamp/`recvWindow` assumption class is therefore also verified on current Spot testnet

That means:
- the standalone signed-path blocker can be cleared
- production-readiness claims still depend on broader gate items outside signed-path proof
