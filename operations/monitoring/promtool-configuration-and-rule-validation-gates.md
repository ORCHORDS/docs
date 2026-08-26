# promtool configuration and rule-validation gates

**Issue:** A malformed Prometheus configuration or rule file can block reloads or leave intended alerts inactive.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Run `promtool check config` and `promtool check rules` with the same Prometheus tool version used in deployment. Add rule unit tests for behavior, because syntax validation alone does not prove alert correctness.

## Controls and verification

- Validate every rendered environment variant.
- Fail CI on parse or rule errors without skipping deployment checks.
- Run tests for pending, firing, and resolved states.
- Confirm referenced files are included in validation.
- Test reload failure preserves the last known-good configuration.
- Canary the runtime reload and inspect server logs/metrics.

## Sources

- [Prometheus: promtool](https://prometheus.io/docs/prometheus/latest/command-line/promtool/)
- [Prometheus: Unit testing rules](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/)
