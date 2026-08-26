# alert-noise-reduction

**Issue:** Reducing false positive alerts and page fatigue without missing real incidents
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Engineers stop responding to alerts because too many are noise. Signal-to-noise ratio is low.

## Pattern / Solution
Audit last 30 days of alerts: tag each as actionable or noise. For noise alerts: increase threshold, add minimum duration, or delete. Use alert burn rate instead of raw thresholds. Implement for clause in Prometheus rules to require sustained condition before firing. Group related alerts into single incident. Use inhibition rules to suppress downstream alerts when root cause alert fires.

## Gotchas
Tracking alert actionability is foundational — without data you are guessing. Aim for less than 5% false positive rate. Never delete an alert without documenting why. Noisy alerts for important signals should be fixed, not silenced permanently.

## Related
alert-grouping-patterns, alert-inhibition-rules, alert-silencing-strategy, slo-alerting-burn-rate
