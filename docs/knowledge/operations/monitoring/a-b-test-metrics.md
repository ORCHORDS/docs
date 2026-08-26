# a-b-test-metrics

**Issue:** Defining and collecting metrics for A/B experiments to measure business impact
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Running experiments without pre-defined metrics leads to hypothesizing after results are known and invalid conclusions.

## Pattern / Solution
Define primary and guardrail metrics before starting any experiment. Primary: the metric the experiment is designed to move (conversion rate, revenue per user). Guardrail: metrics that must not regress (error rate, p99 latency). Collect metrics per variant using feature flag tags. Use a stats framework for significance testing. Track sample ratio mismatch — unequal traffic splits indicate implementation bugs.

## Gotchas
Never run experiments without a pre-registration of metrics and duration. Novelty effect inflates early results for new UI changes — run for full weekly cycles. Long experiments suffer from user composition drift. Guardrail regression should auto-stop the experiment. Statistical significance is not practical significance.

## Related
feature-flag-impact-monitoring, funnel-analytics-monitoring, real-user-monitoring-rum
