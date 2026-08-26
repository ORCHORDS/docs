# Headless macOS runner sleep prevention policy

**Issue**

A registered runner can appear offline or lose network reachability when system sleep is allowed, while globally disabling all power management can hide operational and energy costs.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Set supported macOS power-management policy for AC-powered runner hardware and document intentional display versus system sleep.
- Use `caffeinate` only as a bounded maintenance or job wrapper, not an orphaned permanent process.
- Monitor sleep, wake, network reconnection, and runner listener availability.
- Drain before planned sleep or maintenance and retain compatible capacity elsewhere.

## Verification

1. Leave the Mac without a GUI session across the normal idle window and dispatch a job.
2. Exercise sleep/wake during an unprivileged canary and verify job/check outcome.
3. Remove AC power where hardware policy permits and test the documented response.

## Gotchas

- Display sleep and system sleep differ.
- A process assertion disappears when its process exits.
- Preventing sleep does not guarantee network or service health.

## Official sources

- [Apple pmset manual](https://keith.github.io/xcode-man-pages/pmset.1.html)
- [Apple caffeinate manual](https://keith.github.io/xcode-man-pages/caffeinate.8.html)
