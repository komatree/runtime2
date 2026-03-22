#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODE="${1:-launch}"

RUN_ID="${RUN_ID:-binance-testnet-broader-rehearsal-r5-smoke1}"
REPORTS_DIR="${REPORTS_DIR:-reports}"
LOGS_DIR="${LOGS_DIR:-logs}"
CONFIG_PATH="${CONFIG_PATH:-configs/runtime2_restricted_live_testnet.toml}"
EXECUTION_DATA="${EXECUTION_DATA:-data/binance}"
CONTEXT_DATA="${CONTEXT_DATA:-data/binance}"

# Smoke 목적: 20~30분 내 운영 파이프라인 검증
# runtime CLI가 시간 단위라 1h를 주되, offsets/cycles로 핵심 검증은 30분 안에 끝남
DURATION_HOURS="${DURATION_HOURS:-1}"
CYCLES="${CYCLES:-40}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-30}"
MAX_BLOCKED_MUTATIONS="${MAX_BLOCKED_MUTATIONS:-3}"

SYMBOL="${SYMBOL:-BTCUSDT}"
QTY="${QTY:-0.01}"

# 공백 분리 문자열로 유지
OFFSETS="${OFFSETS:-3 8 13}"
MODES="${MODES:-fill fill fill}"

RUNTIME_SESSION_NAME="${RUNTIME_SESSION_NAME:-smoke_runtime_${RUN_ID##*-}}"
SCHEDULER_SESSION_NAME="${SCHEDULER_SESSION_NAME:-smoke_scheduler_${RUN_ID##*-}}"

RUNTIME_DIR="${REPORTS_DIR}/soak_sessions/${RUN_ID}"
SCHEDULER_RUN_ID="${RUN_ID}-scheduler"
SCHEDULER_DIR="${REPORTS_DIR}/event_exercises/${SCHEDULER_RUN_ID}"

A1_RUN_ID="${RUN_ID}-a1"
A2_RUN_ID="${RUN_ID}-a2"
A3_RUN_ID="${RUN_ID}-a3"

A1_DIR="${REPORTS_DIR}/event_exercises/${A1_RUN_ID}/action_driver"
A2_DIR="${REPORTS_DIR}/event_exercises/${A2_RUN_ID}/action_driver"
A3_DIR="${REPORTS_DIR}/event_exercises/${A3_RUN_ID}/action_driver"

red()   { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
yellow(){ printf '\033[33m%s\033[0m\n' "$*"; }
cyan()  { printf '\033[36m%s\033[0m\n' "$*"; }

die() {
  red "ERROR: $*"
  exit 1
}

require_file() {
  [[ -f "$1" ]] || die "Missing file: $1"
}

require_dir_fresh() {
  local p="$1"
  if [[ -e "$p" ]]; then
    die "Path already exists. Fresh lineage required: $p"
  fi
}

check_tmux() {
  command -v tmux >/dev/null 2>&1 || die "tmux not found. Install tmux first."
}

check_python() {
  command -v python >/dev/null 2>&1 || die "python not found"
  python --version >/dev/null
}

check_env() {
  [[ -n "${BINANCE_API_KEY:-}" ]] || die "BINANCE_API_KEY is not set in current shell"
  [[ -n "${BINANCE_API_SECRET:-}" ]] || die "BINANCE_API_SECRET is not set in current shell"
}

check_repo() {
  require_file "$CONFIG_PATH"
  require_file "scripts/binance_restricted_live_soak.py"
  require_file "scripts/run_broader_action_windows.py"
  require_file "scripts/preflight_broader_rehearsal_wsl.sh"
  [[ -d ".venv" ]] || die "Missing .venv directory under repo root"
}

check_fresh_lineage() {
  require_dir_fresh "$RUNTIME_DIR"
  require_dir_fresh "$SCHEDULER_DIR"
  require_dir_fresh "$A1_DIR"
  require_dir_fresh "$A2_DIR"
  require_dir_fresh "$A3_DIR"
}

session_exists() {
  tmux has-session -t "$1" 2>/dev/null
}

wait_for_file() {
  local path="$1"
  local timeout="${2:-60}"
  local elapsed=0
  while [[ $elapsed -lt $timeout ]]; do
    if [[ -f "$path" ]]; then
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  return 1
}

runtime_session_json() {
  echo "${RUNTIME_DIR}/runtime_session.json"
}

scheduler_manifest_json() {
  echo "${SCHEDULER_DIR}/scheduler_manifest.json"
}

scheduler_events_jsonl() {
  echo "${SCHEDULER_DIR}/scheduler_events.jsonl"
}

tmux_dump() {
  local session_name="$1"
  echo
  cyan "[tmux pane dump: ${session_name}]"
  tmux capture-pane -pt "$session_name" || true
  echo
}

launch_runtime() {
  local cmd
  cmd=$(cat <<EOF
cd "$ROOT_DIR"
source .venv/bin/activate
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
  --output-subdir soak_sessions \
  --max-blocked-mutations "$MAX_BLOCKED_MUTATIONS" \
  --confirm-rehearsal-only \
  --allow-restricted-live-rehearsal \
  --confirm-no-order-submission
EOF
)
  tmux new-session -d -s "$RUNTIME_SESSION_NAME" bash -lc "$cmd"
}

launch_scheduler() {
  local cmd
  cmd=$(cat <<EOF
cd "$ROOT_DIR"
source .venv/bin/activate
python scripts/run_broader_action_windows.py \
  --runtime-run-id "$RUN_ID" \
  --reports-dir "$REPORTS_DIR" \
  --config "$CONFIG_PATH" \
  --symbol "$SYMBOL" \
  --qty "$QTY" \
  --offset-minutes $OFFSETS \
  --modes $MODES
EOF
)
  tmux new-session -d -s "$SCHEDULER_SESSION_NAME" bash -lc "$cmd"
}

print_launch_summary() {
  cyan "=================================================="
  cyan "30분 smoke launch started"
  cyan "=================================================="
  echo "RUN_ID                 : $RUN_ID"
  echo "RUNTIME_SESSION_NAME   : $RUNTIME_SESSION_NAME"
  echo "SCHEDULER_SESSION_NAME : $SCHEDULER_SESSION_NAME"
  echo "RUNTIME_DIR            : $RUNTIME_DIR"
  echo "SCHEDULER_DIR          : $SCHEDULER_DIR"
  echo "OFFSETS                : $OFFSETS"
  echo "MODES                  : $MODES"
  echo
  echo "[attach runtime]"
  echo "tmux attach -t $RUNTIME_SESSION_NAME"
  echo
  echo "[attach scheduler]"
  echo "tmux attach -t $SCHEDULER_SESSION_NAME"
  echo
  echo "[watch runtime cycles]"
  echo "tail -f $RUNTIME_DIR/runtime_cycles.jsonl"
  echo
  echo "[watch scheduler]"
  echo "tail -f $SCHEDULER_DIR/scheduler_events.jsonl"
  echo
  echo "[quick verify]"
  echo "RUN_ID=\"$RUN_ID\" scripts/run_broader_rehearsal_smoke30_wsl.sh verify"
}

verify() {
  cyan "=================================================="
  cyan "30분 smoke verify"
  cyan "=================================================="

  local ok=1

  if [[ -f "$(runtime_session_json)" ]]; then
    green "OK runtime_session.json"
  else
    red "MISSING runtime_session.json"
    ok=0
  fi

  if [[ -f "$(scheduler_manifest_json)" ]]; then
    green "OK scheduler_manifest.json"
  else
    yellow "MISSING scheduler_manifest.json (maybe scheduler not started yet)"
    ok=0
  fi

  for d in "$A1_DIR" "$A2_DIR" "$A3_DIR"; do
    if [[ -d "$d" ]]; then
      green "OK dir $d"
    else
      yellow "WAIT/NO dir $d"
      ok=0
    fi
  done

  for f in \
    "$A1_DIR/action_driver_result.json" \
    "$A2_DIR/action_driver_result.json" \
    "$A3_DIR/action_driver_result.json"
  do
    if [[ -f "$f" ]]; then
      green "OK file $f"
    else
      yellow "WAIT/NO file $f"
      ok=0
    fi
  done

  if [[ -f "$(scheduler_events_jsonl)" ]]; then
    green "OK scheduler_events.jsonl"
    echo
    cyan "[scheduler tail]"
    tail -n 20 "$(scheduler_events_jsonl)" || true

    if grep -q '"event": "scheduler_complete"' "$(scheduler_events_jsonl)"; then
      green "OK scheduler_complete found"
    else
      yellow "scheduler_complete not found yet"
      ok=0
    fi
  else
    red "MISSING scheduler_events.jsonl"
    ok=0
  fi

  if [[ -f "${RUNTIME_DIR}/soak_summary.json" ]]; then
    echo
    cyan "[runtime summary core]"
    python - <<PY
import json, pathlib
p = pathlib.Path("${RUNTIME_DIR}/soak_summary.json")
data = json.loads(p.read_text())
for k in ["stop_reason", "aborted", "blocked_mutation_count", "completed_cycles", "final_exchange_health_state"]:
    print(f"{k}: {data.get(k)}")
PY
  else
    yellow "soak_summary.json not present yet"
    ok=0
  fi

  for suffix in a1 a2 a3; do
    local rf="${REPORTS_DIR}/event_exercises/${RUN_ID}-${suffix}/action_driver/action_driver_result.json"
    if [[ -f "$rf" ]]; then
      echo
      cyan "[${suffix} result]"
      python - <<PY
import json, pathlib
p = pathlib.Path("$rf")
data = json.loads(p.read_text())
for k in ["run_id", "window_outcome", "mandatory_success", "successful_actions", "failed_actions"]:
    print(f"{k}: {data.get(k)}")
print("failure_reasons:", data.get("failure_reasons"))
PY
    fi
  done

  echo
  if [[ "$ok" -eq 1 ]]; then
    green "SMOKE STATUS: likely GO candidate"
  else
    yellow "SMOKE STATUS: not yet GO / or still in progress / or failed criteria"
  fi
}

launch() {
  check_tmux
  check_python
  check_repo
  check_env
  check_fresh_lineage

  if session_exists "$RUNTIME_SESSION_NAME"; then
    die "tmux session already exists: $RUNTIME_SESSION_NAME"
  fi
  if session_exists "$SCHEDULER_SESSION_NAME"; then
    die "tmux session already exists: $SCHEDULER_SESSION_NAME"
  fi

  cyan "Running sourced preflight in current shell..."
  # 부모 셸에서만 preflight. tmux 내부에서는 재실행 금지.
  source scripts/preflight_broader_rehearsal_wsl.sh

  launch_runtime
  green "Runtime tmux session launched: $RUNTIME_SESSION_NAME"

  if wait_for_file "$(runtime_session_json)" 60; then
    green "runtime_session.json detected"
  else
    red "runtime_session.json was not created within 60s"
    tmux_dump "$RUNTIME_SESSION_NAME"
    die "Runtime failed to create runtime_session.json"
  fi

  launch_scheduler
  green "Scheduler tmux session launched: $SCHEDULER_SESSION_NAME"

  print_launch_summary
}

case "$MODE" in
  launch)
    launch
    ;;
  verify)
    verify
    ;;
  *)
    die "Usage: $0 [launch|verify]"
    ;;
esac
