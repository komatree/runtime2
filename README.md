# runtime2

Production-candidate repository skeleton for a candle-based trading runtime.

## Principles

- `runtime2/` is the authoritative codebase.
- Clean architecture and explicit contracts take precedence over convenience.
- Strategy logic is candle-driven and exchange adapters are isolated behind contracts.
- No direct dependency on legacy runtime directories.

## Top-Level Layout

- `app/contracts`: cross-module interfaces and domain contracts
- `app/runtime`: orchestration and lifecycle management
- `app/datafeeds`: market data ingestion and normalization
- `app/features`: candle, index suite, and stablecoin feature pipelines
- `app/strategies`: strategy implementations and router
- `app/risk`: portfolio and order risk controls
- `app/execution`: order intent translation and execution workflows
- `app/exchanges`: exchange-specific adapters behind shared contracts
- `app/portfolio`: positions, balances, and state aggregation
- `app/storage`: persistence and snapshot/event storage
- `app/monitoring`: metrics, health, alerts, and runtime diagnostics
- `app/config`: typed configuration loading and validation
- `docs`: architecture and operator documentation
- `tests`: contract, unit, integration, and simulation tests

## Current Status

This baseline establishes repository boundaries and documentation only. Core runtime behavior, exchange clients, persistence implementations, and strategy logic remain to be implemented.
