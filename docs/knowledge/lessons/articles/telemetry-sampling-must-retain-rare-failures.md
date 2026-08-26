# Telemetry Sampling Must Retain Rare Failures

**Issue:** Uniform head sampling can discard the only traces containing a rare error, while aggressive log sampling can hide the evidence needed to understand a low-frequency high-impact failure.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Define sampling objectives separately for successful traffic, known errors, novel errors, and high-value transactions.
- Use tail or policy-based sampling where a decision depends on completed trace attributes.
- Always retain bounded exemplars and error evidence while controlling duplicate floods.
- Measure effective sampling probability and dropped telemetry by reason.

## Verification

- Inject a rare failure below the normal head-sampling rate and verify evidence survives.
- Generate a repeated error storm and verify rate controls preserve representative examples.
- Reconstruct a sampled incident across metrics, traces, and logs.

## Gotchas

- Tail sampling requires buffering and can lose decisions during collector failure.
- Keeping every error without bounds can turn an incident into a telemetry outage.

## Official sources

- https://opentelemetry.io/docs/concepts/sampling/
- https://opentelemetry.io/docs/collector/
