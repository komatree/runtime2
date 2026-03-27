# runtime2 Next Steps

## Immediate Next Step

Repeat bounded confirmation on the current runtime path with a fresh run id.

Purpose:
- confirm the bounded-stage result is repeatable
- confirm finalization remains stable
- compare reconnect / heartbeat churn against the retained `r6` baseline

Minimum comparison set:
- `soak_summary.json`
- `finalization_debug.json`
- `scheduler_events.jsonl`
- `reconciliation_events.jsonl`
- `reconnect_events.jsonl`

## Near-Term Next Step

Continue reconnect / heartbeat churn analysis.

Current bounded-stage focus:
- measure whether the current reconnect-sensitivity hardening reduces churn materially
- separate:
  - environment contribution
  - watchdog sensitivity

Current stage rule:
- keep fixes local to the Binance transport / bounded operator path
- no websocket-model redesign

## After Reconnect Review

Next bounded-stage hardening candidate:
- reduce exchange-rule caution around `PERCENT_PRICE_BY_SIDE`

Current meaning:
- this is still a known bounded-stage caution
- it is not currently the main runtime failure class

## Promotion Criteria

Before any micro-live entry discussion, the following should be true:
- repeated bounded run evidence remains clean on the current lineage/session model
- finalization continues to complete normally
- scheduler continuity continues to complete normally
- reconciliation continues to converge without manual attention
- reconnect / heartbeat churn is either reduced materially or remains clearly non-destructive and explained
- `PERCENT_PRICE_BY_SIDE` caution is either reduced or clearly bounded and accepted for the next stage decision

## Sequence

1. Repeat bounded 8h confirmation.
2. Review reconnect / heartbeat churn with the new transport-side evidence.
3. If churn remains high, do the next smallest reconnect hardening only.
4. After reconnect behavior is understood, address `PERCENT_PRICE_BY_SIDE` caution reduction.
5. Only then prepare a micro-live entry review.
