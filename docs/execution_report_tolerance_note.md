# executionReport Tolerance Note

## Purpose

This note defines the current tolerance contract for Binance `executionReport` parsing in `runtime2`.

Relevant implementation:
- [`app/exchanges/binance/private_payload_translator.py`](/home/terratunes/code/trading/runtime2/app/exchanges/binance/private_payload_translator.py)

Relevant tests:
- [`tests/exchanges/test_binance_private_payload_translation.py`](/home/terratunes/code/trading/runtime2/tests/exchanges/test_binance_private_payload_translation.py)

## Current Contract

`runtime2` uses explicit required-field mapping for `executionReport`, but it is tolerant of additional optional Binance fields.

Current behavior:

- required lifecycle/fill fields are validated explicitly
- unknown extra fields do not crash translation by themselves
- optional fields such as `eR` / `expiryReason` are currently tolerated and ignored
- these fields are not currently preserved in canonical runtime contracts
- these fields are not currently normalized into a separate internal expiry-reason field

## What Is Verified

Verified by tests:

1. `executionReport` without `eR` / `expiryReason` translates normally
2. `executionReport` with `eR` / `expiryReason` present still translates safely
3. `executionReport` with unrelated unexpected extra fields still translates safely
4. malformed payloads still fail visibly as `MALFORMED`

## Why The Current Behavior Is Acceptable

For the current project stage:
- lifecycle correctness matters more than preserving every Binance-specific metadata field
- ignoring optional exchange-native metadata is safer than leaking venue shape into strategy or portfolio contracts
- the translator still fails closed on missing required lifecycle data

## What Is Not Yet Done

Not yet implemented:
- canonical internal normalization of expiry reason metadata
- operator-visible reporting of `eR` / `expiryReason`

That is acceptable for now because these fields are not required for the current restricted-live safety gate.

## Misinterpretation To Avoid

- tolerance does not mean silent corruption
- ignored optional fields are intentionally dropped at the adapter boundary
- required-field validation still applies
