# Navigation Timing confidence weighting

**Issue:** RUM aggregates every navigation duration as equally representative. The current Navigation Timing draft can expose a randomized confidence signal, and filtering or averaging it naively can bias results rather than remove noisy samples.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** experimental draft field; feature-detect

## Controls and implementation

Read the single `PerformanceNavigationTiming` entry and preserve the raw duration, navigation cohort, `confidence.value`, and `confidence.randomizedTriggerRate` only when supported. Version the telemetry schema and keep an explicit unsupported cohort; never synthesize a confidence value for older engines.

When estimating high/low cohort means or percentiles, apply the debiasing weights defined by the specification for each record and retain negative weights. Do not drop “low” records or group only by the exposed label. Validate that the sum of weights is numerically usable before publishing an estimate and retain ordinary unweighted navigation metrics as the stable comparison during rollout.

## Verification

Test unsupported/null confidence, trigger rates near zero and one, high/low labels, negative weights, near-zero total weight, small samples, reload/back-forward navigation, transient CPU pressure, and mixed browser versions. Compare an implementation against worked synthetic distributions.

## Gotchas

The field is a Working Draft and can change. Confidence reflects transient representativeness, not device quality or user value; the specification forbids basing it on permanent device/profile traits. The exposed label is randomized, so naive filtering creates bias.

## Sources

- W3C Web Performance WG, [Navigation Timing Level 2](https://www.w3.org/TR/navigation-timing-2/#dom-performancenavigationtiming-confidence)
