# Durable Objects PITR Recovery Runbook

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** Documented

## Problem

Point-in-time recovery (PITR) is an operational recovery mechanism, not an ordinary application mutation. A rushed restore can discard valid writes, recover the wrong object, or leave callers writing while the recovery boundary moves.

## Scope and boundary

Cloudflare exposes PITR only for SQLite-backed Durable Objects. It restores the complete embedded database for one object, including SQL data and values written through the key-value Storage API. It does not restore other Durable Objects, D1, R2, KV, Queues, or external side effects.

Cloudflare retains recoverable history for the previous 30 days. PITR is unavailable in local development because local storage does not maintain the required durable change log.

## Controlled recovery flow

1. Identify the exact namespace, object ID, incident window, and recovery owner.
2. Stop or reject new mutating work for that logical entity.
3. Record the current bookmark and incident evidence.
4. Resolve the desired timestamp with `getBookmarkForTime()`; treat the result as approximate to the requested time and validate business invariants.
5. Call `onNextSessionRestoreBookmark(target)` and securely retain its returned pre-recovery bookmark. That bookmark is the undo point.
6. Intentionally restart the object with `ctx.abort()` so restoration occurs in the next session.
7. Verify schema version, critical rows, idempotency records, alarms, and downstream reconciliation state before reopening writes.
8. If verification fails, use the retained pre-recovery bookmark for a controlled undo.

## Controls

- Require two-person approval for production recovery.
- Never derive the object ID from untrusted incident text without authoritative lookup.
- Keep the target and undo bookmarks out of public logs.
- Quiesce or fence writers; PITR alone does not reconcile external payments, messages, or APIs.
- Preserve an audit record containing object identity, requested timestamp, selected bookmark, approvers, verification results, and reopen time.
- Rehearse against a non-production SQLite-backed namespace; do not claim local PITR testing.

## Verification tests

- Restore a known test object and confirm SQL plus Storage API values move together.
- Confirm a write made after the target bookmark disappears.
- Confirm the returned undo bookmark restores the pre-recovery state.
- Confirm writes remain fenced until verification succeeds.
- Confirm another object and external resources remain unchanged.
- Exercise failure after scheduling but before restart, and restart before verification.

## Gotchas

- A Worker version rollback does not roll back Durable Object storage.
- PITR is per object, not a namespace-wide transaction.
- A successful API call is not proof that business state is consistent.
- Bookmarks are opaque recovery coordinates; do not invent semantic meaning beyond documented ordering.

## Official sources

- [SQLite-backed Durable Object Storage — PITR API](https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/)
- [SQLite in Durable Objects generally available](https://developers.cloudflare.com/changelog/post/2025-04-07-sqlite-in-durable-objects-ga/)
- [New Durable Object namespaces must use SQLite storage](https://developers.cloudflare.com/changelog/post/2026-07-09-restrict-new-kv-backed-namespaces/)
