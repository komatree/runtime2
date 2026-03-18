#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUN_STEM="${RUN_STEM:-binance-testnet-broader-rehearsal}"
CONFIG_PATH="${CONFIG_PATH:-configs/runtime2_restricted_live_testnet.toml}"
SYMBOL="${SYMBOL:-BTCUSDT}"
QTY="${QTY:-0.01}"
RUNTIME_START_ISO="${RUNTIME_START_ISO:-}"
OFFSET_MINUTES_1="${OFFSET_MINUTES_1:-20}"
OFFSET_MINUTES_2="${OFFSET_MINUTES_2:-140}"
OFFSET_MINUTES_3="${OFFSET_MINUTES_3:-260}"

source scripts/preflight_broader_rehearsal_wsl.sh

if [[ -z "$RUNTIME_START_ISO" ]]; then
  echo "ERROR: RUNTIME_START_ISO is required"
  echo "Example: 2026-03-17T22:15:00+09:00"
  exit 1
fi

echo "=================================================="
echo "Terminal 2: broader action window scheduler"
echo "=================================================="
echo "RUN_STEM=$RUN_STEM"
echo "RUNTIME_START_ISO=$RUNTIME_START_ISO"
echo "SYMBOL=$SYMBOL"
echo "QTY=$QTY"
echo "OFFSETS=$OFFSET_MINUTES_1 $OFFSET_MINUTES_2 $OFFSET_MINUTES_3"

python scripts/run_broader_action_windows.py \
  --runtime-start-iso "$RUNTIME_START_ISO" \
  --run-stem "$RUN_STEM" \
  --config "$CONFIG_PATH" \
  --symbol "$SYMBOL" \
  --qty "$QTY" \
  --offset-minutes "$OFFSET_MINUTES_1" "$OFFSET_MINUTES_2" "$OFFSET_MINUTES_3" \
  --modes fill fill fill

