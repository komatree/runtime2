#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODE="${1:-launch}"

RUN_ID="${RUN_ID:-binance-testnet-broader-rehearsal-r5}"
REPORTS_DIR="${REPORTS_DIR:-reports}"
LOGS_DIR="${LOGS_DIR:-logs}"
CONFIG_PATH="${CONFIG_PATH:-configs/runtime2_restricted_live_testnet.toml}"
EXECUTION_DATA="${EXECUTION_DATA:-data/binance}"
CONTEXT_DATA="${CONTEXT_DATA:-data/binance}"

DURATION_HOURS="${DURATION_HOURS:-6}"
CYCLES="${CYCLES:-720}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-30}"
MAX_BLOCKED_MUTATIONS="${MAX_BLOCKED_MUTATIONS:-3}"

SYMBOL="${SYMBOL:-BTCUSDT}"
QTY="${QTY:-0.01}"
OFFSETS="${OFFSETS:-20 140 260}"
MODES="${MODES:-fill fill fill}"

RUNTIME_SESSION_NAME="${RUNTIME_SESSION_NAME:-broad6h_runtime_${RUN_ID##*-}}"
SCHEDULER_SESSION_NAME="${SCHEDULER_SESSION_NAME:-broad6h_scheduler_${RUN_ID##*-}}"

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
  cyan "6h broader rehearsal launch started"
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
  echo "[auto watch]"
  echo "RUN_ID=\"$RUN_ID\" scripts/run_broader_rehearsal_6h_wsl.sh watch"
  echo
  echo "[final verify]"
  echo "RUN_ID=\"$RUN_ID\" scripts/run_broader_rehearsal_6h_wsl.sh verify"
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

  if wait_for_file "$(scheduler_manifest_json)" 60; then
    green "scheduler_manifest.json detected"
  else
    red "scheduler_manifest.json was not created within 60s"
    tmux_dump "$SCHEDULER_SESSION_NAME"
    die "Scheduler failed to create scheduler_manifest.json"
  fi

  print_launch_summary
}

watch_mode() {
  command -v watch >/dev/null 2>&1 || die "watch not found"
  watch -n 15 "
echo '=== runtime process ==='
pgrep -af binance_restricted_live_soak.py || true
echo
echo '=== scheduler process ==='
pgrep -af run_broader_action_windows.py || true
echo
echo '=== runtime dir ==='
ls -lt '$RUNTIME_DIR' 2>/dev/null | head -n 8 || true
echo
echo '=== scheduler tail ==='
tail -n 10 '$(scheduler_events_jsonl)' 2>/dev/null || true
echo
echo '=== a1 result ==='
python - <<'PY'
import json, pathlib
p = pathlib.Path('$A1_DIR/action_driver_result.json')
print(json.loads(p.read_text())['window_outcome'] if p.exists() else 'not yet')
PY
echo
echo '=== a2 result ==='
python - <<'PY'
import json, pathlib
p = pathlib.Path('$A2_DIR/action_driver_result.json')
print(json.loads(p.read_text())['window_outcome'] if p.exists() else 'not yet')
PY
echo
echo '=== a3 result ==='
python - <<'PY'
import json, pathlib
p = pathlib.Path('$A3_DIR/action_driver_result.json')
print(json.loads(p.read_text())['window_outcome'] if p.exists() else 'not yet')
PY
"
}

verify() {
  cyan "=================================================="
  cyan "6h broader rehearsal verify"
  cyan "=================================================="

  local ok=1

  [[ -f "$(runtime_session_json)" ]] && green "OK runtime_session.json" || { red "MISSING runtime_session.json"; ok=0; }
  [[ -f "$(scheduler_manifest_json)" ]] && green "OK scheduler_manifest.json" || { red "MISSING scheduler_manifest.json"; ok=0; }

  for d in "$A1_DIR" "$A2_DIR" "$A3_DIR"; do
    [[ -d "$d" ]] && green "OK dir $d" || { red "MISSING dir $d"; ok=0; }
  done

  for f in \
    "$A1_DIR/action_driver_result.json" \
    "$A2_DIR/action_driver_result.json" \
    "$A3_DIR/action_driver_result.json"
  do
    [[ -f "$f" ]] && green "OK file $f" || { red "MISSING file $f"; ok=0; }
  done

  if [[ -f "$(scheduler_events_jsonl)" ]]; then
    green "OK scheduler_events.jsonl"
    echo
    cyan "[scheduler tail]"
    tail -n 30 "$(scheduler_events_jsonl)" || true
    grep -q '"event": "scheduler_complete"' "$(scheduler_events_jsonl)" && green "OK scheduler_complete found" || { red "scheduler_complete missing"; ok=0; }
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
    red "MISSING soak_summary.json"
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
    green "FINAL STATUS: likely PASS candidate / ready for Codex formal review"
  else
    yellow "FINAL STATUS: incomplete / caution / failure indicators present"
  fi
}

case "$MODE" in
  launch)
    launch
    ;;
  watch)
    watch_mode
    ;;
  verify)
    verify
    ;;
  *)
    die "Usage: $0 [launch|watch|verify]"
    ;;
esac
