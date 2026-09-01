# Argo Rollouts Canary Metric Analysis

**Issue:** Argo Rollouts can shift traffic between versions based on metric analysis, but the metric definitions themselves are where most teams fail. A canary that advances based on irrelevant or noisy metrics produces a green status on a deployment that is silently degrading the user experience. Operators need a structured method for selecting, defining, and validating analysis templates before trusting them with promotion decisions.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The Analysis Phase

Argo Rollouts models a deployment as a sequence of steps, each step declaring a traffic shift and an optional set of queries. A query is a measurement specification that the rollout controller submits to a metrics provider (Prometheus, Datadog, New Relic, CloudWatch, etc.) at each analysis interval. The provider returns one or more metric values; the analysis template applies the configured success or failure criteria to those values and emits a status.

A step pauses if an analysis is configured. Traffic shifts to the new version, the controller waits for the analysis interval, submits the query, evaluates the result, and either advances to the next step or aborts back to the stable version. The whole process can run for minutes or hours depending on the step durations and interval configuration. This pause-and-measure is what makes the rollout safer than a continuous percentage ramp.

## Choosing The Right Metrics

The metrics that matter are the ones that move on real user-visible regressions and stay quiet on ordinary noise. Error rate, request rate, and latency percentiles are the canonical trio, but each has subtleties. Error rate must be measured on the canary version's traffic specifically, not cluster-wide, because a parallel incident on the stable version can mask canary regressions. Latency percentiles should use p95 or p99 depending on service-level objectives; p50 is too noisy to gate a promotion.

Application-level metrics matter as much as infrastructure metrics when the service has distinctive business logic. A payment service should track transaction success rate; a content service should track cache hit rate. The metric must be observable from the same point where canary traffic terminates, because if the metric is computed at a different hop than the request, the canary analysis will be measuring something other than the canary itself.

## Constructing An AnalysisTemplate

An AnalysisTemplate is a CRD that defines a reusable set of queries and evaluation criteria. Each query has an inline metric specification (for built-in providers) or a reference to a provider-specific measurement. The template also carries a list of arguments that callers can substitute, so the same template can be used across multiple rollouts with different service names or label selectors.

A well-formed template uses at least two independent metrics: one for the canary's intrinsic health (error rate) and one for comparative health (canary latency versus stable latency). The failure criteria should be a single threshold per metric, with explicit units. Avoid chained booleans that obscure the failure signal; the operator investigating a failure should be able to read the template and immediately understand which metric tripped and what threshold it crossed.

## Analysis Run History And Retries

Argo Rollouts stores the result of each analysis run in a `AnalysisRun` resource. The resource includes the start time, end time, the metric values returned, and the success or failure status. Operators investigating a failed promotion should consult the AnalysisRun before reading controller logs, because the run captures the exact values that were observed and the criteria that failed.

Retries on transient metric providers are configured per analysis template with `count` and `interval` parameters. A reasonable default is three retries with a one-minute interval, so that a single missed Prometheus scrape does not fail an otherwise healthy canary. Higher retry counts hide real regressions; shorter intervals amplify noise. Configure retries deliberately and review the AnalysisRun history periodically to ensure retries are not masking genuine issues.

## Failure Modes

The most damaging failure is an analysis template that is syntactically valid but semantically equivalent to "always pass." This happens when the query references a metric that does not exist, or references an instance label that the rollout does not set, so the provider returns an empty series and the success criterion is vacuously true. Defend against this by writing a chaos test that deliberately injects a regression and asserts the rollout aborts; if the rollout proceeds, the analysis template is broken.

A second failure is the metric provider itself being down. Argo Rollouts marks the analysis as inconclusive rather than failing it, which is correct behavior because a missing metric should not fail a rollout that may be healthy. But operators who interpret inconclusive as failed and force-promote anyway bypass the entire safety net. Configure notifications to alert on inconclusive analyses and require human review before manual promotion under those conditions.

A third failure is treating the canary analysis as a one-time check rather than a continuous signal. A service whose latency degrades only after two hours of steady traffic cannot be detected by an analysis that runs for five minutes. Lengthen the analysis interval or schedule a soak test in the analysis template, and ensure that the final promotion step has a duration long enough to catch steady-state regressions that warm-up traffic would mask.

## Canonical sources

1. https://argo-rollouts.readthedocs.io/en/stable/analysis/
2. https://argo-rollouts.readthedocs.io/en/stable/features/specification/