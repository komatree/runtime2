# Binance Signed Path Verification Plan

## Goal

Prove that runtime2 signed Binance Spot paths behave correctly on current Spot testnet and do not regress into `-1022 INVALID_SIGNATURE` failures.

Primary focus:
- signed REST order/status requests
- signed WS-API user data subscription
- special-character parameter safety where Binance allows the parameter values
- percent-encode-before-HMAC expectations

## Why This Needs Explicit Verification

Current runtime2 status:
- signed REST order lookup exists in [`app/exchanges/binance/order_client.py`](/home/terratunes/code/trading/runtime2/app/exchanges/binance/order_client.py)
- signed WS-API user-data subscription exists in [`app/exchanges/binance/private_transport.py`](/home/terratunes/code/trading/runtime2/app/exchanges/binance/private_transport.py)
- transport/unit coverage exists for happy-path signing and subscription wiring

What is still missing:
- explicit live testnet evidence that current signing logic matches Binance Spot 2026 expectations
- explicit reserved/special-character safety coverage
- explicit `INVALID_SIGNATURE` failure-prevention evidence

## Preconditions

1. Use the dedicated Spot testnet rehearsal config:
   - [`configs/runtime2_restricted_live_testnet.toml`](/home/terratunes/code/trading/runtime2/configs/runtime2_restricted_live_testnet.toml)
2. Use Spot testnet credentials only.
3. Keep restricted-live fail-closed flags enabled.
4. Record all verification artifacts under a dedicated operator-reviewed directory.

Suggested output root:
- `reports/signed_path_verification/<run_id>/`

## Verification Areas

### 1. Signed REST order-status lookup

Target:
- prove `GET /api/v3/order` succeeds with runtime2 signing on Spot testnet

Current code:
- [`app/exchanges/binance/order_client.py`](/home/terratunes/code/trading/runtime2/app/exchanges/binance/order_client.py)

Checks:
- request includes `timestamp`
- request includes `recvWindow`
- request includes `signature`
- request header includes `X-MBX-APIKEY`
- response is not `-1022 INVALID_SIGNATURE`
- status-query health records `success`

Evidence to preserve:
- request URL shape with sensitive values redacted
- response status
- final `BinanceStatusQueryHealth`

### 2. Signed WS-API user-data subscription

Target:
- prove `userDataStream.subscribe.signature` succeeds on Spot testnet with the current runtime2 adapter bootstrap

Current code:
- [`app/exchanges/binance/private_transport.py`](/home/terratunes/code/trading/runtime2/app/exchanges/binance/private_transport.py)

Checks:
- authenticated WS-API connection opens
- `userDataStream.subscribe.signature` request is accepted
- subscription acknowledgement includes `subscriptionId`
- runtime2 session metadata records bootstrap method and subscription id
- no fallback to deprecated REST listenKey bootstrap occurs

Evidence to preserve:
- bootstrap summary
- authenticated subscription acknowledgement summary
- resulting private-session metadata

### 3. Special-character parameter safety

Goal:
- prove or sharply bound the risk that encoding/signing fails when request parameters contain characters needing encoding

Important constraint:
- only use characters Binance allows for the specific field under test
- if Binance rejects a value because the value itself is invalid, that does not prove a signing bug

Recommended split:
- unit/integration verification for raw encoding behavior
- live testnet verification only with Binance-allowed value patterns

REST candidates:
- `origClientOrderId` lookup path if the chosen values are allowed by Binance

Unit-level checks:
- capture the pre-sign query string
- assert percent-encoded canonical query construction
- compare produced signature with expected HMAC over the encoded string

Live checks:
- use a Binance-allowed `origClientOrderId` variant containing the widest safe character set allowed by venue rules
- verify no `-1022 INVALID_SIGNATURE`

### 4. Failure-prevention / negative verification

Goal:
- prove runtime2 would surface signature issues clearly rather than silently misclassifying them

Checks:
- `BinanceStatusQueryHealth` reports failure cleanly on signed REST errors
- private WS-API bootstrap failure remains operator-visible
- runtime2 remains fail-closed on signature failure

Evidence to preserve:
- operator-visible error summary
- final exchange-health state
- final soak/rehearsal summary with blocked mutation if applicable

## Concrete Verification Steps

### Step 1. Local capture test for REST signing

Add or run a transport-level test that:
- injects a fake `urlopen`
- records the exact outgoing query string
- verifies encoded parameter ordering and signature
- includes at least one value needing encoding if the field permits it

Success condition:
- expected encoded query string and signature match exactly

### Step 2. Local capture test for WS-API signing

Add or run a websocket-factory capture test that:
- records the exact `userDataStream.subscribe.signature` payload
- verifies request method
- verifies `apiKey`, `timestamp`, `recvWindow`, and `signature`
- compares signature against the expected canonical string used by the adapter

Success condition:
- subscription payload matches runtime2 canonical signing rules

### Step 3. Live Spot testnet REST lookup verification

Run a controlled status lookup on testnet using current runtime2 adapter code.

Success condition:
- request succeeds
- no `-1022`
- health state is `success`

### Step 4. Live Spot testnet WS-API bootstrap verification

Run a restricted-live rehearsal bootstrap or private transport bootstrap check against Spot testnet.

Success condition:
- subscription ack succeeds
- no deprecated listenKey path is hit
- resulting session metadata is populated

### Step 5. Combined rehearsal verification

Run a short restricted-live rehearsal or soak validation with testnet config and verify:
- private bootstrap succeeds
- signed status-query health remains visible if recovery is exercised
- no signature-related degradation occurs

## Suggested Artifact Set

Under `reports/signed_path_verification/<run_id>/` persist:
- `rest_lookup_check.json`
- `ws_subscription_check.json`
- `signed_path_summary.md`
- `signed_path_summary.json`

If live rehearsal is used, also retain:
- exchange health snapshot
- restricted-live summary
- any reconciliation or blocked-mutation evidence

## Pass Criteria

All of the following must hold:
- signed REST lookup succeeds on Spot testnet without `-1022`
- signed WS-API bootstrap succeeds on Spot testnet without deprecated bootstrap fallback
- signature failures are operator-visible and fail-closed in negative tests
- at least one explicit encoding-oriented test exists in the repo for signed-path construction

## Current Expected Gaps Before This Plan Is Executed

Likely current status:
- REST signing is probably correct for current status lookups
- WS-API subscription signing is probably operational for current simple params
- special-character safety is not yet explicitly proven
- live testnet evidence for current signing rules is not yet preserved as a dedicated verification artifact

## Conservative Conclusion

runtime2 is close on signed-path implementation, but still needs explicit verification evidence. The goal of this plan is not to add broad new features. It is to remove ambiguity around current Binance Spot signing behavior and to prevent future `-1022 INVALID_SIGNATURE` surprises.
