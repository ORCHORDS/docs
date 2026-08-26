# MCP cancellation side-effect boundary

**Issue:** An MCP cancellation notification requests that work stop but cannot prove a remote side effect did not already commit.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Propagate abort signals, define cancellable phases, persist idempotency/outcome for mutations, acknowledge final state separately.

## Tests

Cancel before dispatch, during I/O, before/after commit, duplicate cancellation, disconnected client.

## Gotchas

Cancellation is best effort; never map it directly to rollback success.

## Official sources

- https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/cancellation
