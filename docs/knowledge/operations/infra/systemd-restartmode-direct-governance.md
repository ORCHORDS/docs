# systemd RestartMode=direct governance

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Problem

Direct restart transitions can skip failed/inactive states and dependency notifications, hiding failure semantics from operators and dependent units.

## When to use

Use only for services whose transient failures should restart without propagating an unhealthy state to dependencies.

## Controls

Set bounded restart limits, preserve watchdog and exit-status checks, alert on restart counters, and document dependency semantics.

## Implementation

Canary RestartMode=direct with explicit Restart and StartLimit settings; observe unit state transitions and dependent behavior; keep a rollback drop-in.

## Tests

Test crash loops, watchdog expiry, clean stop, dependency failure, manual restart, rate limiting, and host reboot.

## Gotchas

Faster state transitions do not make an unhealthy service healthy and must not suppress required checks.

## Official sources

- [Official documentation](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html)
