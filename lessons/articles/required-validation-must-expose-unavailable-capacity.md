# Required validation must expose unavailable capacity

**Lesson:** When a required platform has no matching runner, silently skipping or converting the job to success turns missing capacity into false confidence.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Operationalization

Use a stable required check that fails or remains visibly blocked when its target is unavailable; define an approved exception with owner and expiry.

## Verification

Take the runner offline, exhaust concurrency, and mismatch labels; verify merge/release cannot appear fully validated.

## Gotchas

A queued job is not a passed check, and a conditional skip can satisfy branch protection depending on workflow design.

## Official sources

- https://docs.github.com/en/actions/reference/runners/self-hosted-runners
- https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks
