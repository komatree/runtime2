# runtime2 2-Minute Pre-Run Checklist

## Purpose

Use this checklist immediately before any bounded operator run.

This is a short operator gate for the current `runtime2` bounded stage.
It does not replace the longer operating-PC checklist or the full operator runbook.

## Checklist

- Confirm the target run is still `restricted_live_rehearsal` on Binance Spot testnet.
- Confirm a fresh `RUN_ID` will be used.
- Confirm old tmux sessions for the intended wrapper run are cleared.
- Confirm `BINANCE_API_KEY` and `BINANCE_API_SECRET` are loaded in the current shell through the hidden-prompt preflight path.
- Confirm the local runtime data bundle exists:
  - `data/binance/btcusdt_4h.json`
  - `data/binance/btcusdt_1d.json`
- Confirm `reports/` and `logs/` are writable.
- Confirm the host is on AC power and sleep / hibernate are disabled for the intended run duration.
- Confirm the intended wrapper is the bounded-stage wrapper:
  - [`scripts/run_broader_rehearsal_6h_wsl.sh`](/home/terratunes/code/trading/runtime2/scripts/run_broader_rehearsal_6h_wsl.sh)
- Confirm the expected post-run evidence set is known in advance:
  - `soak_summary.json`
  - `finalization_debug.json`
  - `scheduler_events.jsonl`
  - `reconciliation_events.jsonl`
  - `reconnect_events.jsonl`

## Fast Verification Commands

```bash
ls -l data/binance
test -f data/binance/btcusdt_4h.json
test -f data/binance/btcusdt_1d.json
tmux ls
```

## Fail-Closed Reminder

Do not:
- reuse an interrupted run id
- resume an interrupted bounded run
- treat missing final runtime artifacts as a soft warning

If the run later shows missing final runtime artifacts, inspect:
- `reports/soak_sessions/<run_id>/finalization_debug.json`
