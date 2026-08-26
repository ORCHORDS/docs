# Alertmanager UTF-8 strict matcher migration

**Issue**

Fallback parsing can hide classic matcher syntax that will fail or change meaning under UTF-8 strict mode.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Run `amtool check-config --enable-feature=utf8-strict-mode` in CI.
- Quote matcher values and escape backslashes; review parser-disagreement warnings individually.
- Canary strict mode before fleet rollout and compare route, silence, and inhibition matches.
- Block deployment on any fallback warning; retain a tested rollback flag.

## Verification

1. Test empty values, Unicode, regex escapes, routes, silences, and inhibition rules.
2. Replay representative label sets against old and strict parsers and diff receiver selection.
3. Verify reload failure leaves the previous valid configuration active.

## Gotchas

- Fallback success is not strict compatibility.
- A matcher valid in both parsers can still have different meaning.
- Classic mode is temporary rollback, not migration completion.

## Official source

- [Official documentation](https://prometheus.io/docs/alerting/latest/configuration/#label-matchers)
