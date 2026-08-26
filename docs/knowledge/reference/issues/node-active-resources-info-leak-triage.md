# Node active-resource info leak triage

**Issue:** `process.getActiveResourcesInfo()` reports resource-type strings keeping the event loop alive. It is useful for teardown triage, but it does not identify owning objects or prove that a resource is leaked.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Capture a baseline after startup and a second snapshot after deterministic teardown; compare resource types across repeated isolated runs. Pair counts with subsystem-owned lifecycle logs and explicit close/dispose assertions. Keep diagnostic output free of payloads and secrets.

## Tests

Intentionally retain a timer, server, socket, worker, and file watcher; verify each changes the expected resource-type evidence. Exercise normal completion, assertion failure, cancellation, and signal shutdown.

## Gotchas

Resource names are implementation-level types, counts can include legitimate runtime work, and an unchanged list can still conceal replacement churn. Do not turn a heuristic snapshot into a flaky exact global assertion.

## Official sources

- https://nodejs.org/api/process.html#processgetactiveresourcesinfo
