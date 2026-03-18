#!/usr/bin/env bash
set -euo pipefail

RUN_ID="${1:-}"
if [[ -z "$RUN_ID" ]]; then
  echo "Usage: bash scripts/check_soak_result.sh <run_id>"
  exit 1
fi

BASE="reports/soak_sessions/${RUN_ID}"

echo "===== RUN_ID ====="
echo "$RUN_ID"
echo

if [[ ! -d "$BASE" ]]; then
  echo "Run directory not found: $BASE"
  exit 2
fi

echo "===== FILES ====="
find "$BASE" -maxdepth 2 -type f | sort
echo

REQUIRED=(
  "health_transitions.jsonl"
  "reconnect_events.jsonl"
  "listen_key_refresh.jsonl"
  "reconciliation_events.jsonl"
  "soak_summary.json"
  "soak_summary.md"
)

echo "===== REQUIRED ARTIFACT CHECK ====="
missing=0
for f in "${REQUIRED[@]}"; do
  if [[ -f "$BASE/$f" ]]; then
    echo "[OK] $f"
  else
    echo "[MISSING] $f"
    missing=1
  fi
done
echo

if [[ -f "$BASE/soak_summary.json" ]]; then
  echo "===== SOAK SUMMARY JSON ====="
  cat "$BASE/soak_summary.json"
  echo
fi

if [[ -f "$BASE/soak_summary.md" ]]; then
  echo "===== SOAK SUMMARY MD ====="
  sed -n '1,220p' "$BASE/soak_summary.md"
  echo
fi

if [[ -f "$BASE/health_transitions.jsonl" ]]; then
  echo "===== HEALTH TRANSITIONS (tail 10) ====="
  tail -n 10 "$BASE/health_transitions.jsonl"
  echo
fi

if [[ -f "$BASE/reconciliation_events.jsonl" ]]; then
  echo "===== RECONCILIATION EVENTS (tail 10) ====="
  tail -n 10 "$BASE/reconciliation_events.jsonl"
  echo
fi

if [[ -f "$BASE/reconnect_events.jsonl" ]]; then
  echo "===== RECONNECT EVENTS (tail 10) ====="
  tail -n 10 "$BASE/reconnect_events.jsonl"
  echo
fi

if [[ -f "$BASE/listen_key_refresh.jsonl" ]]; then
  echo "===== LISTEN KEY REFRESH EVENTS (tail 10) ====="
  tail -n 10 "$BASE/listen_key_refresh.jsonl"
  echo
fi

echo "===== QUICK CHECK ====="
echo "- stop_reason == completed ?"
echo "- aborted == false ?"
echo "- final_exchange_health_state is healthy or explainable degraded ?"
echo "- refresh_failures == 0 ?"
echo "- reconnect_count acceptable ?"
echo "- heartbeat_overdue_events == 0 ?"
echo "- fatal/manual_attention/max_blocked_mutations 없나?"
echo "- blocked mutation / no private payload alerts가 설명 가능한가?"
echo

if [[ "$missing" -ne 0 ]]; then
  echo "RESULT: FAIL (missing required artifacts)"
  exit 3
fi

echo "RESULT: ARTIFACTS PRESENT - review summary fields now"
