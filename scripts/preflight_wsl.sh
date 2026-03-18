#!/usr/bin/env bash
set -Eeuo pipefail

echo "=================================================="
echo "Binance Testnet Credentials Input"
echo "=================================================="

# 1) API Key 입력
read -rp "Enter BINANCE_API_KEY: " INPUT_API_KEY
if [[ -z "${INPUT_API_KEY:-}" ]]; then
  echo "ERROR: BINANCE_API_KEY is empty"
  exit 1
fi

# 2) API Secret 입력 (입력값 숨김)
read -rsp "Enter BINANCE_API_SECRET (hidden): " INPUT_API_SECRET
echo
if [[ -z "${INPUT_API_SECRET:-}" ]]; then
  echo "ERROR: BINANCE_API_SECRET is empty"
  exit 1
fi

# 3) 요약 확인
echo "=================================================="
echo "You entered:"
echo "  BINANCE_API_KEY    : ${INPUT_API_KEY:0:8}********"
echo "  BINANCE_API_SECRET : ******** (hidden)"
read -rp "Use these credentials? [y/N]: " CONFIRM
CONFIRM=${CONFIRM:-N}

if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
  echo "Aborted by user."
  exit 1
fi

# 4) 현재 셸 환경변수로 설정
export BINANCE_API_KEY="$INPUT_API_KEY"
export BINANCE_API_SECRET="$INPUT_API_SECRET"

# ---------------------------------------------------
# 여기부터 기존 preflight 로직
# ---------------------------------------------------

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "=================================================="
echo "Preflight: runtime2 broader rehearsal (WSL)"
echo "=================================================="
echo "ROOT_DIR: $ROOT_DIR"

if [[ -z "${BINANCE_API_KEY:-}" ]]; then
  echo "ERROR: BINANCE_API_KEY is not set"
  exit 1
fi

if [[ -z "${BINANCE_API_SECRET:-}" ]]; then
  echo "ERROR: BINANCE_API_SECRET is not set"
  exit 1
fi

if [[ ! -f "configs/runtime2_restricted_live_testnet.toml" ]]; then
  echo "ERROR: config file not found"
  exit 1
fi

if [[ ! -f "scripts/binance_restricted_live_soak.py" ]]; then
  echo "ERROR: runtime entrypoint missing"
  exit 1
fi

if [[ ! -f "scripts/run_broader_action_windows.py" ]]; then
  echo "ERROR: broader action scheduler missing"
  exit 1
fi

if [[ ! -f "scripts/run_testnet_event_action_driver.py" ]]; then
  echo "ERROR: action driver missing"
  exit 1
fi

echo "Python: $(command -v python || true)"
python --version

echo "Timezone check:"
date --iso-8601=seconds

echo "Repo artifact paths:"
mkdir -p reports logs data/binance
echo "  reports/"
echo "  logs/"
echo "  data/binance/"

echo "Optional credential smoke check..."
if [[ -f "scripts/check_binance_testnet_credentials.py" ]]; then
  python scripts/check_binance_testnet_credentials.py || {
    echo "ERROR: testnet credential check failed"
    exit 1
  }
fi

echo "Preflight OK"
