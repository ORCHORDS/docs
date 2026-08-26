# Alertmanager silence storage limits

**Problem**

Unlimited silence count or size can consume memory and degrade alert administration.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use for multi-tenant or automation-heavy Alertmanager installations.

## Controls

- Set maximum silence count and per-silence bytes from measured use.
- Preserve authorization, expiration, and emergency response.
- Alert before limits block legitimate incident work.

## Implementation

Pin flags across HA peers, audit automation, and maintain break-glass cleanup.

## Tests

Test boundary count and size, expired silences, HA replication, reload, and restart.

## Gotchas

- Limits can block emergency writes.
- HA peers need aligned settings.
- Retained expired state affects capacity planning.

## Official sources

- [Alertmanager limits](https://prometheus.io/docs/alerting/latest/configuration/#limits)
