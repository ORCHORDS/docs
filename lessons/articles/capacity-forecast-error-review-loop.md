# Capacity Forecast Error Review Loop

**Issue:** Capacity plans fail when teams track only outages or current utilization and never compare forecast demand with actual demand.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Store each forecast with horizon, assumptions, uncertainty range, and accountable owner.
- Compare forecast to actual demand and saturation signals at a fixed cadence; retain directional and absolute error.
- Separate workload growth error from per-request resource-cost changes and infrastructure delivery delays.
- Turn repeated bias into model or provisioning-policy changes, not larger undocumented buffers.

## Verification

- Backtest the forecast over several historical windows.
- Simulate demand above the upper confidence bound and verify scaling and procurement lead-time responses.
- Confirm each major error produces a reviewed corrective action.

## Gotchas

- Average utilization hides hotspots and tail saturation.
- A forecast without a decision deadline cannot protect long-lead capacity.

## Official sources

- https://sre.google/workbook/non-abstract-design/
- https://sre.google/sre-book/software-engineering-in-sre/
