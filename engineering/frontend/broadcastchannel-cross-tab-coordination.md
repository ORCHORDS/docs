# BroadcastChannel cross-tab coordination

**Issue:** Tabs use `BroadcastChannel` as if it were durable, ordered shared state. A suspended, newly opened, partitioned, or crashed context can miss messages, while simultaneous writers overwrite each other's assumptions.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation

Use a channel only for ephemeral same-origin notifications. Put authoritative state in a transactional store or server and send small invalidation messages containing schema version, entity key, revision, sender instance, and event ID. On receipt, validate the structured-cloned payload and reread the authoritative record.

Make handlers idempotent and tolerate duplicates, gaps, and reordering across independent producers. Generate a random per-context ID to suppress self-originated work without treating it as identity. Close channels when the owning lifecycle ends, bound message size and handler work, and use explicit leader leases if exactly one tab must perform a task.

## Verification

Test two simultaneous writers, a tab opened after an event, background suspension, back/forward cache, reload, crash, storage partition differences, private browsing, malformed payloads, clone failures, and high-rate broadcasts. Assert convergence comes from rereading state, not replaying every message.

## Gotchas

BroadcastChannel has no retained history, acknowledgement, access-control message envelope, or delivery guarantee to contexts that are not active. A shared channel name is not a security boundary, and storage partitioning can prevent otherwise same-origin contexts from communicating.

## Sources

- WHATWG, [HTML Living Standard: broadcasting to other browsing contexts](https://html.spec.whatwg.org/multipage/web-messaging.html#broadcasting-to-other-browsing-contexts)
