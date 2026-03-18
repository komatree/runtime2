#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUN_ID="${RUN_ID:-binance-testnet-broader-rehearsal-r3}"
CONFIG_PATH="${CONFIG_PATH:-configs/runtime2_restricted_live_testnet.toml}"
EXECUTION_DATA="${EXECUTION_DATA:-data/binance}"
CONTEXT_DATA="${CONTEXT_DATA:-data/binance}"
REPORTS_DIR="${REPORTS_DIR:-reports}"
LOGS_DIR="${LOGS_DIR:-logs}"
DURATION_HOURS="${DURATION_HOURS:-6}"
CYCLES="${CYCLES:-720}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-30}"
MAX_BLOCKED_MUTATIONS="${MAX_BLOCKED_MUTATIONS:-3}"
OUTPUT_SUBDIR="${OUTPUT_SUBDIR:-soak_sessions}"

source scripts/preflight_broader_rehearsal_wsl.sh

echo "=================================================="
echo "Terminal 1: runtime2 broader rehearsal"
echo "=================================================="
echo "RUN_ID=$RUN_ID"
echo "DURATION_HOURS=$DURATION_HOURS"
echo "CYCLES=$CYCLES"
echo "POLL_INTERVAL_SECONDS=$POLL_INTERVAL_SECONDS"

python scripts/binance_restricted_live_soak.py \
  --config "$CONFIG_PATH" \
  --execution-data "$EXECUTION_DATA" \
  --context-data "$CONTEXT_DATA" \
  --reports-dir "$REPORTS_DIR" \
  --logs-dir "$LOGS_DIR" \
  --exchange-mode restricted_live_rehearsal \
  --run-id "$RUN_ID" \
  --duration-hours "$DURATION_HOURS" \
  --cycles "$CYCLES" \
  --poll-interval-seconds "$POLL_INTERVAL_SECONDS" \
  --output-subdir "$OUTPUT_SUBDIR" \
  --max-blocked-mutations "$MAX_BLOCKED_MUTATIONS" \
  --confirm-rehearsal-only \
  --allow-restricted-live-rehearsal \
  --confirm-no-order-submission
