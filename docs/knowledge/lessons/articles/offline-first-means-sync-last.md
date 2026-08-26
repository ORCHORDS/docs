# offline-first-means-sync-last

**Issue:** Offline-first mobile apps that treat sync as an afterthought produce conflict storms and data loss when users reconnect
**Date:** 2026-08-11
**Status:** documented

## What happened
A field-service mobile app allowed offline edits. When reconnecting, it uploaded all changes using a simple "last write wins" strategy. A supervisor and a field tech both edited the same work order while offline. On reconnect, the supervisor's changes silently overwrote the tech's completed status. Work orders appeared incomplete. Technicians were re-dispatched to jobs already done.

## The lesson
Offline-first requires designing a conflict resolution strategy before writing the first line of sync code. Decide upfront: last write wins, server wins, client wins, merge by field, or manual resolution. The sync mechanism is not a feature you add at the end — it is the core of the data model.

## Why it matters
Conflict resolution in distributed data is hard. Getting it wrong means silent data loss or overwrites that users cannot detect or recover from. The design complexity must be confronted at the start, not discovered during QA when the wrong data has already been accepted.

## How to apply
- [ ] Define your conflict resolution strategy in the technical design document before building.
- [ ] Use vector clocks, CRDTs, or operational transforms for complex merging scenarios.
- [ ] Surface conflicts to users when automatic resolution is ambiguous — don't silently pick a winner.
- [ ] Write tests that simulate: two devices editing the same record offline, then both syncing.
- [ ] Build a sync log that records every operation, not just the final state, to enable conflict detection.

## Related
- `mobile-first-means-api-first.md`
- `eventual-consistency-surprises-clients.md`
