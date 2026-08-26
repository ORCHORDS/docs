# MCP roots list-changed reconciliation

**Issue:** Client roots can change during a session; cached filesystem authority becomes stale when list_changed is ignored.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Treat roots as allowlisted hints, re-list on notification, canonicalize paths, cancel/re-authorize work outside new roots.

## Tests

Remove/rename root mid-call, symlink escape, duplicate roots, missed notification, reconnect.

## Gotchas

Roots do not grant OS permission and notification delivery is not a transaction barrier.

## Official sources

- https://modelcontextprotocol.io/specification/2025-06-18/client/roots
