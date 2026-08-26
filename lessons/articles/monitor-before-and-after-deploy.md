# monitor-before-and-after-deploy

**Issue:** Deploying without establishing a pre-deploy baseline makes it impossible to detect regressions quickly
**Date:** 2026-08-11
**Status:** documented

## What happened
A backend service deployed a new caching layer. Error rates were "normal" but p99 latency climbed from 120 ms to 1.4 s. Nobody noticed for two hours because the alerting threshold was set to absolute error count, not latency. Users churned silently. The root cause (cache stampede) was only found by correlating logs manually after a customer complaint.

## The lesson
Capture a metric snapshot (error rate, p50/p95/p99 latency, throughput, saturation) immediately before deploying. Keep the deploy runbook open alongside the dashboard. Define "healthy" before you flip the switch so you can declare "unhealthy" objectively within five minutes.

## Why it matters
Without a baseline you cannot tell if a degradation predates the deploy. Noise in monitoring is interpreted as "things look fine" rather than "we broke something subtle." Slow regressions are found by customers before engineers.

## How to apply
- [ ] Screenshot or annotate the key dashboard at T-5 minutes before deploy.
- [ ] Set deploy markers in your APM tool so graphs show the exact deploy timestamp.
- [ ] Watch metrics for 15 minutes post-deploy before closing the incident channel.
- [ ] Configure latency-based alerts (not just error-count alerts) before deploy, not after.
- [ ] Define rollback trigger criteria in the runbook (e.g., "if p99 > 500 ms for 3 minutes, roll back").

## Related
- `feature-flags-before-code-changes.md`
- `health-checks-must-check-dependencies.md`
- `write-the-runbook-before-the-incident.md`
