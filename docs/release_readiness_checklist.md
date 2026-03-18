# Release Readiness Checklist

Use this checklist before any restricted-live review. This is a blocking checklist, not a suggestion list.

## Release Metadata

- Date:
- Operator:
- Commit or workspace state:
- Mode under review: `restricted_live`

## Required Test Gates

- `contracts` passed
- `features` passed
- `strategies` passed
- `runtime_mode` passed
- `report_only_integration` passed
- `paper_integration` passed
- `observability` passed
- `exchanges` passed
- `reconciliation` passed
- `regression` passed

## Required Documentation State

- [`docs/data_contracts.md`](/home/terratunes/code/trading/runtime2/docs/data_contracts.md) current
- [`docs/runtime_flow.md`](/home/terratunes/code/trading/runtime2/docs/runtime_flow.md) current
- [`docs/exchange_integration_notes.md`](/home/terratunes/code/trading/runtime2/docs/exchange_integration_notes.md) current
- [`docs/debugging_playbook.md`](/home/terratunes/code/trading/runtime2/docs/debugging_playbook.md) current
- [`docs/operator_runbook.md`](/home/terratunes/code/trading/runtime2/docs/operator_runbook.md) current
- [`docs/restricted_live_readiness.md`](/home/terratunes/code/trading/runtime2/docs/restricted_live_readiness.md) current

## Runtime Observability Checks

- report-only cycle records present
- paper transition records present
- runtime cycle summary records present
- latest health/status snapshot present
- operator markdown status report present
- degraded flags visible when optional sources are absent
- alerts visible at cycle level

## Binance Blocker Checks

- private stream contract reviewed
- private stream gap visibility confirmed
- reconciliation workflow reviewed
- unknown execution recovery visibility confirmed
- clock sync status visibility confirmed
- order lookup by `client_order_id` reviewed
- order lookup by `exchange_order_id` reviewed
- unresolved production gaps disclosed explicitly

## Rollback Readiness

- rollback trigger review completed
- fallback mode identified: `paper` or `report_only`
- artifacts retention path confirmed
- open-gap disclosure recorded

## Decision

- allow restricted-live review
- block restricted-live review

## Notes

- 
