# runtime2 Account Snapshot Bootstrap

- `configs/runtime2_restricted_live_testnet.toml` now enables `bootstrap_from_account_snapshot = true`.
- When enabled for restricted-live rehearsal, [`scripts/binance_restricted_live_soak.py`](/home/terratunes/code/trading/runtime2/scripts/binance_restricted_live_soak.py) fetches one signed REST Spot account snapshot before the soak loop starts.
- That snapshot is converted into the initial portfolio baseline so the session starts from real testnet BTC/USDT balances instead of synthetic `initial_cash` only.
- The bootstrap remains explicit and reviewable via:
  - `bootstrap_portfolio_alignment.json` in the run directory
- This does not weaken fail-closed behavior. The safety gate still blocks on true mismatches after bootstrap.
