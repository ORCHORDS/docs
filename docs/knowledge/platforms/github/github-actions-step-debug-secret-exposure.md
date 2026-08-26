# GitHub Actions step-debug secret exposure boundary

**Issue:** Runner debug logging increases command/environment detail and can expose transformed secrets or sensitive paths.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Restrict ACTIONS_STEP_DEBUG to approved reruns, minimize secrets, use test credentials, review/delete logs and rotate on exposure.

## Tests

Debug fork/no-secret job, transformed token, multiline output, artifact/log retention.

## Gotchas

Masking is not guaranteed for transformed values; debug must not become repository default.

## Official sources

- https://docs.github.com/en/actions/how-tos/monitor-workflows/enable-debug-logging
