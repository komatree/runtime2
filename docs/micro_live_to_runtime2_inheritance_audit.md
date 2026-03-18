# Micro-Live To runtime2 Inheritance Audit

## Purpose

This audit checks whether `runtime2` is carrying forward the operational strengths of the existing micro-live system while intentionally replacing the parts that were structurally insufficient for the new architecture.

This is not a claim that micro-live architecture should be copied wholesale.
It is a check against avoidable re-learning of already solved operator workflow lessons.

## Sources Reviewed

### Existing micro-live reference

- [`../v16clean_ref/scripts/run_micro_live_scheduled.cmd`](/home/terratunes/code/trading/v16clean_ref/scripts/run_micro_live_scheduled.cmd)
- [`../v16clean_ref/scripts/preflight_binance.py`](/home/terratunes/code/trading/v16clean_ref/scripts/preflight_binance.py)
- [`../v16clean_ref/scripts/summarize_live_run.py`](/home/terratunes/code/trading/v16clean_ref/scripts/summarize_live_run.py)
- [`../v16clean_ref/scripts/soak_testnet_24h.py`](/home/terratunes/code/trading/v16clean_ref/scripts/soak_testnet_24h.py)
- [`../v16clean_ref/docs/runbook_live_ops.md`](/home/terratunes/code/trading/v16clean_ref/docs/runbook_live_ops.md)
- [`../v16clean_ref/docs/micro_live_prelaunch_checklist.md`](/home/terratunes/code/trading/v16clean_ref/docs/micro_live_prelaunch_checklist.md)
- [`../v16clean_ref/tests/test_preflight.py`](/home/terratunes/code/trading/v16clean_ref/tests/test_preflight.py)
- [`../v16clean_ref/tests/test_live_guard.py`](/home/terratunes/code/trading/v16clean_ref/tests/test_live_guard.py)

### runtime2

- [`scripts/preflight_runtime2.sh`](/home/terratunes/code/trading/runtime2/scripts/preflight_runtime2.sh)
- [`scripts/run_report_only.sh`](/home/terratunes/code/trading/runtime2/scripts/run_report_only.sh)
- [`scripts/run_paper.sh`](/home/terratunes/code/trading/runtime2/scripts/run_paper.sh)
- [`scripts/run_restricted_live.sh`](/home/terratunes/code/trading/runtime2/scripts/run_restricted_live.sh)
- [`scripts/runtime2_rehearsal.py`](/home/terratunes/code/trading/runtime2/scripts/runtime2_rehearsal.py)
- [`scripts/binance_restricted_live_soak.py`](/home/terratunes/code/trading/runtime2/scripts/binance_restricted_live_soak.py)
- [`scripts/binance_restricted_live_soak_campaign.py`](/home/terratunes/code/trading/runtime2/scripts/binance_restricted_live_soak_campaign.py)
- [`scripts/check_soak_result.sh`](/home/terratunes/code/trading/runtime2/scripts/check_soak_result.sh)
- [`app/config/rehearsal.py`](/home/terratunes/code/trading/runtime2/app/config/rehearsal.py)
- [`docs/operator_runbook.md`](/home/terratunes/code/trading/runtime2/docs/operator_runbook.md)
- [`docs/restricted_live_readiness.md`](/home/terratunes/code/trading/runtime2/docs/restricted_live_readiness.md)

## Executive Verdict

`runtime2` has inherited the important operational pattern categories correctly in several areas:

- thin launch wrappers
- preflight gating
- operator-visible summaries
- fail-closed posture
- staged soak practice

It has also intentionally replaced micro-live choices that were structurally insufficient:

- env-only launch semantics
- single live-path behavior
- sqlite-only post-run summarization as the main operator surface
- direct micro-live promotion logic

However, some operating-PC lessons were not fully carried over:

- explicit OS/power/network preparation
- signed auth-check as a pre-launch operator step
- explicit operator halt policy for repeated exchange error classes
- explicit graceful external stop convention for long-running soak sessions

Those gaps are operational, not architectural. They are the main areas where runtime2 is still re-learning lessons that micro-live had already written down.

## Item Classification

| Item | micro-live evidence | runtime2 evidence | Classification | Why |
| --- | --- | --- | --- | --- |
| Launch / wrapper flow | [`run_micro_live_scheduled.cmd`](/home/terratunes/code/trading/v16clean_ref/scripts/run_micro_live_scheduled.cmd) sets env, validates secrets, prints safe summary, then runs one launcher command | [`preflight_runtime2.sh`](/home/terratunes/code/trading/runtime2/scripts/preflight_runtime2.sh), [`run_paper.sh`](/home/terratunes/code/trading/runtime2/scripts/run_paper.sh), [`run_restricted_live.sh`](/home/terratunes/code/trading/runtime2/scripts/run_restricted_live.sh) are thin wrappers over [`runtime2_rehearsal.py`](/home/terratunes/code/trading/runtime2/scripts/runtime2_rehearsal.py) | inherited correctly | runtime2 kept the proven “small wrapper -> one authoritative launcher” pattern and improved it with explicit subcommands per mode |
| Preflight safety checks | [`preflight_binance.py`](/home/terratunes/code/trading/v16clean_ref/scripts/preflight_binance.py) checks provider, mode, base URL, credentials, market-only restriction; tests in [`test_preflight.py`](/home/terratunes/code/trading/v16clean_ref/tests/test_preflight.py) | [`validate_runtime_rehearsal`](/home/terratunes/code/trading/runtime2/app/config/rehearsal.py) checks config/data presence, writable paths, credentials, exchange mode, rehearsal confirmations, order submission disabled | inherited correctly | runtime2 clearly inherited the fail-before-launch mindset and widened it from env checks to full config/path/mode validation |
| Monitoring / reporting | micro-live had post-run summarization via [`summarize_live_run.py`](/home/terratunes/code/trading/v16clean_ref/scripts/summarize_live_run.py) and live summary markdown; ops docs require logs + reports | runtime2 persists JSONL cycle reports, `runtime_health.json`, `runtime_status.md`, soak artifacts, and post-run helper [`check_soak_result.sh`](/home/terratunes/code/trading/runtime2/scripts/check_soak_result.sh) | intentionally replaced | runtime2 replaced sqlite-centric summarization with richer structured observability. This is a good replacement, not lost inheritance |
| Operator runbooks | [`runbook_live_ops.md`](/home/terratunes/code/trading/v16clean_ref/docs/runbook_live_ops.md) and [`micro_live_prelaunch_checklist.md`](/home/terratunes/code/trading/v16clean_ref/docs/micro_live_prelaunch_checklist.md) define staged operation, stop rules, incident response, local PC notes | [`operator_runbook.md`](/home/terratunes/code/trading/runtime2/docs/operator_runbook.md) and [`restricted_live_readiness.md`](/home/terratunes/code/trading/runtime2/docs/restricted_live_readiness.md) define staged rehearsal, artifacts, rollback, observability | inherited correctly, with gaps | runtime2 carried over operator-facing docs and rollback thinking, but some practical PC-operation lessons are missing explicitly |
| Fail-closed behavior | micro-live guard halts on `UnknownExecutionError`, `IpBannedError`, and repeated same-subclass errors in [`test_live_guard.py`](/home/terratunes/code/trading/v16clean_ref/tests/test_live_guard.py) | runtime2 blocks restricted-live on missing prerequisites, unresolved reconciliation, mutation ambiguity, and quality blockers in [`app/config/rehearsal.py`](/home/terratunes/code/trading/runtime2/app/config/rehearsal.py) and [`docs/restricted_live_readiness.md`](/home/terratunes/code/trading/runtime2/docs/restricted_live_readiness.md) | inherited correctly | runtime2 did not regress here; it is more explicit and broader than micro-live |
| Long-running operational practice | micro-live explicitly stages `testnet soak -> summarize -> micro-live` in [`runbook_live_ops.md`](/home/terratunes/code/trading/v16clean_ref/docs/runbook_live_ops.md) and [`soak_testnet_24h.py`](/home/terratunes/code/trading/v16clean_ref/scripts/soak_testnet_24h.py) | runtime2 has dedicated restricted-live soak runner, campaign, summaries, and evidence review path in [`scripts/binance_restricted_live_soak.py`](/home/terratunes/code/trading/runtime2/scripts/binance_restricted_live_soak.py) and [`scripts/binance_restricted_live_soak_campaign.py`](/home/terratunes/code/trading/runtime2/scripts/binance_restricted_live_soak_campaign.py) | inherited correctly | runtime2 correctly preserved the staged soak discipline and made the evidence artifacts stronger |
| Testnet/mainnet separation | micro-live preflight enforces dry/testnet vs real/mainnet URL separation in [`preflight_binance.py`](/home/terratunes/code/trading/v16clean_ref/scripts/preflight_binance.py) | runtime2 now uses separate config and endpoint-profile validation, including [`configs/runtime2_restricted_live_testnet.toml`](/home/terratunes/code/trading/runtime2/configs/runtime2_restricted_live_testnet.toml) | inherited correctly | runtime2 initially had some confusion here, but the current state now matches the good operational lesson |
| Signed auth-check before launch | micro-live checklist requires `--auth-check` before launch in [`micro_live_prelaunch_checklist.md`](/home/terratunes/code/trading/v16clean_ref/docs/micro_live_prelaunch_checklist.md) | runtime2 preflight only checks credential presence and config/path validity; it does not yet expose a separate signed auth probe in the operator path | missing / insufficiently inherited | this is one area where runtime2 is still re-learning an already solved lesson |
| Local PC operations checklist | micro-live runbook explicitly calls out sleep/hibernate, updates, network stability, clock sync in [`runbook_live_ops.md`](/home/terratunes/code/trading/v16clean_ref/docs/runbook_live_ops.md) and [`micro_live_prelaunch_checklist.md`](/home/terratunes/code/trading/v16clean_ref/docs/micro_live_prelaunch_checklist.md) | runtime2 startup checklist is higher level in [`operator_runbook.md`](/home/terratunes/code/trading/runtime2/docs/operator_runbook.md) and does not explicitly carry forward those PC-level checks | missing / insufficiently inherited | this is avoidable duplicated trial-and-error risk on the operating PC |
| External graceful stop convention | micro-live soak loop supports a STOP file and signal-aware chunked sleep in [`soak_testnet_24h.py`](/home/terratunes/code/trading/v16clean_ref/scripts/soak_testnet_24h.py) | runtime2 has duration/abort criteria and bounded reads, but no operator-documented STOP-file or equivalent external soft-stop convention for soak runs | missing / insufficiently inherited | runtime2 can be stopped, but the operating practice is less explicit than the older system |

## What runtime2 Correctly Inherited

### 1. Thin launcher wrappers

micro-live did not require operators to memorize deep internal entrypoints. That pattern remains intact in runtime2:

- wrappers stay small
- the real logic lives in one authoritative launcher
- operators get a stable command surface

This is the right inheritance, and runtime2 improves it by separating `report_only`, `paper`, and `restricted_live` cleanly.

### 2. Preflight before action

micro-live already knew that most bad launches are environment/config mistakes, not strategy mistakes.
runtime2 preserved that lesson and made it stronger:

- config path presence
- data path presence
- writable artifact paths
- credentials presence
- mode-specific exchange-mode lock
- explicit rehearsal confirmations
- hard block on order submission

This is not trial-and-error repetition. It is a clear inheritance and upgrade.

### 3. Operator-visible summaries

micro-live had a good habit of producing reviewable summaries after runs.
runtime2 preserved the operational principle, but intentionally replaced the implementation:

- structured JSONL instead of only sqlite summarization
- `runtime_health.json`
- `runtime_status.md`
- soak session artifacts
- post-run review helper script

This is a strong inheritance of the practice, not the exact mechanism.

### 4. Staged long-running rehearsal

micro-live used testnet soak as a confidence-building step before real micro-live.
runtime2 preserved the staged evidence mindset:

- validation soak
- multi-hour soak sessions
- documented thresholds
- post-run review flow

That is one of the clearest cases where runtime2 did not forget an already solved lesson.

### 5. Fail-closed live attitude

micro-live’s live guard halted on specific dangerous classes.
runtime2 inherited the underlying lesson and generalized it:

- missing prerequisites halt the run
- invalid mode/env combinations halt the run
- unresolved reconciliation halts live-facing mutation
- ambiguous translation blocks mutation
- restricted-live quality blockers fail closed

This is an intentional strengthening, not a loss.

## What runtime2 Intentionally Changed And Why

### 1. Env-only launcher semantics were replaced by explicit config-driven launch

This is correct.

micro-live was operationally successful with env-heavy launch flow, but runtime2 needs:

- typed launch config
- separate runners
- explicit instrument/timeframe inputs
- explicit exchange endpoint profile

That is a structural replacement required by the new architecture.

### 2. Single live-path mindset was replaced by mode-separated runners

This is correct.

micro-live’s operating success does not mean its behavior path should be copied directly.
runtime2 intentionally keeps:

- `report_only`
- `paper`
- `restricted_live`

as distinct runtime paths. That is the correct architectural change.

### 3. sqlite-first postmortem was replaced by richer real-time observability

This is also correct.

The micro-live summary script was useful, but runtime2 needed:

- continuous status snapshots
- exchange-health rollups
- append-only cycle records
- soak-specific JSONL evidence

This replacement is justified and operationally better.

## What Was Not Fully Carried Over

### 1. Signed auth-check as a pre-launch operator step

micro-live explicitly required a signed auth probe before launch.
runtime2 currently checks credentials exist, but that is weaker than proving:

- the key is valid
- the secret matches
- the endpoint/profile pair is actually usable

This is the clearest avoidable lesson that was not fully inherited.

### 2. PC-level operations checklist

micro-live runbooks explicitly captured the operating-PC realities:

- disable sleep / hibernate
- avoid forced restarts
- keep stable network
- keep clock sync enabled

runtime2’s operator docs are good on runtime artifacts and gates, but they do not carry those concrete workstation lessons forward clearly enough.

This is a real operational inheritance gap.

### 3. Explicit halt policy for repeated exchange-error classes

micro-live had a concrete guard policy:

- immediate halt on specific classes
- halt on repeated same-class errors

runtime2 has stronger structural blockers overall, but the operator-facing docs do not yet state an equally concrete repetitive-error halt policy for long-running restricted-live rehearsal.

This is partially inherited in code posture, but insufficiently inherited in operator practice.

### 4. Explicit external soft-stop convention

micro-live soak had a clear STOP-file and chunked sleep design.
runtime2 now has bounded duration and abort criteria, which is better than before, but the explicit operator convention for “request stop safely without kill -9 style interruption” is still less concrete.

This is not a severe blocker, but it is an operational lesson that was already known.

## Avoidable Duplicated Trial-And-Error

The clearest areas where runtime2 appears to have re-learned known operational lessons are:

1. testnet/mainnet separation had to be rediscovered and made explicit later instead of being first-class from the start
2. bounded soak stop behavior had to be fixed after real operation exposed the issue
3. signed auth-probe discipline is still weaker than the older system’s prelaunch practice
4. operating-PC checklist discipline is less explicit than the older system, even though that lesson was already learned

These are not catastrophic, but they are exactly the kind of avoidable operational rediscovery the user is worried about.

## Recommended Corrections

1. Add an explicit restricted-live signed auth-check command or preflight extension.
   - Keep it read-only.
   - Make it part of the operator checklist before longer soak sessions.

2. Carry forward the operating-PC checklist into runtime2 docs explicitly.
   - sleep / hibernate
   - forced updates / restart windows
   - network stability
   - clock sync state

3. Add operator-facing halt policy language for repeated exchange-health degradation.
   - repeated reconnect churn
   - repeated renewal failure
   - repeated unknown/private-truth loss
   - repeated clock uncertainty

4. Document one explicit graceful external stop convention for long-running soak sessions.
   - signal handling is acceptable
   - a STOP-file or equivalent explicit operator procedure would be better

## Bottom Line

`runtime2` did not ignore micro-live’s successful operational patterns.
It inherited the important ones:

- wrappers
- preflight
- summaries
- staged soak discipline
- fail-closed posture

The main misses are not in architecture. They are in practical operator workflow carry-over:

- signed auth-check
- PC-level launch hygiene
- explicit repeated-error halt policy
- explicit graceful soak-stop convention

So the verdict is:

- runtime2 has inherited the major successful operational patterns correctly
- runtime2 has intentionally replaced the structurally insufficient parts correctly
- runtime2 still has a few avoidable operational lessons that were not fully carried over from the operating micro-live system
