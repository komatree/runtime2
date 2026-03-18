# runtime2 Operating PC Checklist

## Purpose

Use this checklist before any Binance rehearsal, especially any long-running restricted-live soak.

This checklist is about workstation safety and operational stability.
It does not prove runtime correctness by itself.

## 1. Power And Sleep

Confirm all of the following:

- sleep is disabled or strictly controlled for the full expected run window
- hibernate is disabled or strictly controlled for the full expected run window
- lid-close behavior will not suspend the machine unexpectedly
- the machine is connected to stable power for long runs
- battery-only execution is avoided for long-running soak sessions

If any of these are not true:
- do not start a long-running soak

## 2. OS Update And Restart Risk

Confirm all of the following:

- no scheduled reboot is expected during the run window
- OS auto-update will not force a restart during the run window
- package manager or desktop updater is not about to interrupt the session
- antivirus or endpoint tooling is not scheduled for a disruptive scan/reboot event

If restart risk is unclear:
- do not start the soak yet

## 3. Network Stability Expectations

Confirm all of the following:

- the machine is on a stable network path
- Wi-Fi roaming or unstable hotspot use is avoided when possible
- VPN/proxy behavior is understood before launch
- firewall or security software is not expected to interrupt websocket traffic

If the machine is on a fragile network:
- expect degraded exchange health
- do not over-diagnose runtime2 before ruling out the network first

## 4. Clock Sync And Time Drift Awareness

Confirm all of the following:

- OS time sync is enabled
- system clock appears correct before launch
- recent manual time edits have not been made
- NTP drift or time-source problems are not already known on the machine

If clock state is suspicious:
- do not start signed-path verification or long-running soak

## 5. Disk And Log Space

Confirm all of the following:

- `reports/` target has enough free space
- `logs/` target has enough free space
- no filesystem quota or permission issue is expected
- there is enough room for JSONL artifacts and summaries for the planned run duration

If free space is low:
- do not start the run until space is cleared

## 6. Process And Terminal Stability

Confirm all of the following:

- the terminal/session running the soak will stay open
- remote shell timeout risk is understood if using SSH
- tmux/screen or an equivalent stable session wrapper is used for longer runs when possible
- no conflicting local job will compete heavily for CPU, memory, or network

## 7. Config And Credential Sanity

Confirm all of the following:

- correct config file selected for the environment
- Spot testnet config used for Spot testnet rehearsal:
  - [`configs/runtime2_restricted_live_testnet.toml`](/home/terratunes/code/trading/runtime2/configs/runtime2_restricted_live_testnet.toml)
- credentials match the intended environment
- no mainnet/testnet mix-up exists

Run this read-only local sanity check before any live signed-path or private-bootstrap attempt:

```bash
python scripts/check_binance_testnet_credentials.py \
  --config configs/runtime2_restricted_live_testnet.toml
```

Interpretation:
- `api_key_shape_ok: False`
  - likely placeholder, truncation, quoting damage, or wrong env loading path
- `api_key_equals_secret: True`
  - likely incorrect export/injection
- `placeholder_like_value_detected: True`
  - stop immediately and reload credentials correctly
- `testnet_profile_ok: False` or `testnet_hosts_ok: False`
  - likely mainnet/testnet mismatch

## 8. Pre-Launch Checklist

Complete this exact order:

1. complete this operating-PC checklist
2. run launcher preflight
3. run the signed/bootstrap validation procedure from [`docs/runtime2_operator_runbook.md`](/home/terratunes/code/trading/runtime2/docs/runtime2_operator_runbook.md)
4. only then start a longer soak session

## 9. During The Run

Watch for:

- sleep or screen-lock policies changing unexpectedly
- network transitions
- exchange health turning `degraded` or `fatal`
- repeated reconnect or renewal issues
- repeated clock uncertainty

If any of those occur repeatedly:
- halt the session
- preserve artifacts
- do not proceed to a longer soak step

## 10. After The Run

Review:

- `soak_summary.json`
- `soak_summary.md`
- `runtime_health.json`
- `runtime_status.md`
- `health_transitions.jsonl`
- `reconnect_events.jsonl`
- `listen_key_refresh.jsonl`
- `reconciliation_events.jsonl`

Then ask:

- was the session clean
- was it only idle-stream evidence
- was there any operator/PC issue that explains the result better than runtime2 itself

## 11. Do Not Misinterpret

- a clean workstation does not prove runtime correctness
- a bad workstation can easily create misleading transport failures
- a clean idle soak does not prove active private-event correctness
- a runtime issue should not be declared until PC/environment causes are checked first
