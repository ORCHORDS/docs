# eventual-consistency-ux-design

**Issue:** The backend is eventually consistent — CQRS read models lag writes, replicas trail primaries, and multi-region replication converges over seconds. The database is behaving exactly as designed, yet users file bugs: their just-submitted comment is missing from the list, their profile still shows the old avatar, a colleague sees a stale total. These are not backend defects; they are UX failures to design for asynchrony. Figma's engineering write-up on its multiplayer system shows the shape of the fix: clients apply changes optimistically, suppress server updates that conflict with unacknowledged local edits, and keep working offline indefinitely. Systems need a deliberate eventual-consistency UX contract covering read-your-writes, optimistic updates, rollback, and convergence signals, instead of leaving each screen to improvise.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Core Principles

1. **Read-your-writes is a session guarantee you must build.** After a user writes, subsequent reads by that user must reflect it. Implement via session pinning to the shard that accepted the write, a client-side echo of pending writes layered over server reads, or version-token gating that blocks the read until the view catches up.
2. **Optimistic UI is the primary latency-hiding tool.** Apply the user's action locally and immediately (Figma clients apply property changes without waiting for server acknowledgement) and reconcile with the authoritative response later. This converts replication lag from a user-visible stall into an occasional silent correction.
3. **Never let stale server data clobber fresher local state.** Figma's clients "discard incoming changes from the server that conflict with unacknowledged property changes" to avoid flicker. Any optimistic UI needs the same rule: an inbound update older than a pending local edit for the same field is dropped until the local edit resolves.
4. **Design the failure path as carefully as the happy path.** When the server rejects the optimistic update, roll back visibly with an inline error and a retry affordance — not a silent vanish, and not a toast the user can't act on.
5. **Conflicts must be defined at property granularity.** Figma resolves only true collisions — two clients changing the same property of the same object — while unrelated edits never conflict. Last-writer-wins per property (never per document) keeps the blast radius of a conflict tiny and its resolution comprehensible.
6. **Convergence should be observable.** UI states should distinguish "confirmed" from "pending" from "syncing," so users build an accurate mental model. Pending indicators should be delayed (~1s) so fast paths stay visually quiet.

## Implementation Approaches

1. **Pending-write overlay.** Keep a client-side log of unacknowledged mutations; when rendering, merge it over the server response for the affected entities. Clear entries when the write confirms (matching on id and version) and reconcile when the server result differs from the prediction.
2. **Sticky sessions / shard affinity.** Route a user's requests to the replica or node that served their write for the duration of a session (or until the read model's lag watermark passes the write's timestamp). This buys read-your-writes without any strong-consistency reads.
3. **Versioned reads with gating.** Tag writes with a monotonic version or timestamp; the client sends "at least version N" on read, and the API either waits briefly or returns a "stale" flag plus the older view. This makes lag explicit and testable.
4. **Latency compensation for lists and counters.** Insert new items at the expected position immediately, adjust counts locally, and accept small reflow when the server order arrives. Suppress the reflow if the delta only involves the user's own pending items.
5. **Offline queue with replay.** Following Figma's reconnect model: on reconnection, download fresh server state, replay local edits on top, and resume syncing. Connection logic stays simple; complexity lives in the merge rules.
6. **Structured merge fields where users co-edit.** For collaborative surfaces, use fractional indexing for ordering (Figma stores sibling order as fractions between 0 and 1 so inserts never renumber) and per-property atomic values so merges never produce half-composed results.
7. **Undo that respects other people's edits.** Figma's rule: undoing, copying, and redoing back to the present must not change the document — undo rewrites redo history rather than clobbering teammates' later edits. Naive undo stacks corrupt multiplayer state.

## Gotchas and Failure Modes

1. **Optimistic UI lies during outages.** If the client shows success for minutes while the backend is down, users build on state that never persisted. Bound optimism: after N seconds unacknowledged, degrade the UI to an explicit "saving..." or offline state.
2. **Duplicate submissions on retry.** Optimistic retries without idempotency keys create ghost records that the merge layer then has to deduplicate. Pair every optimistic mutation with a client-generated idempotency token.
3. **Ghost rollback flicker.** Server echoes of the user's own write can arrive and be rendered as if they were new remote edits, briefly re-rendering identical state. Deduplicate by write id before applying.
4. **Cross-entity reads break the illusion.** The write to entity A confirms quickly, but a dashboard aggregating A and B still lags B. Screens that aggregate multiple read models need per-screen gating or a "last updated" affordance, not per-entity gating.
5. **Clock-based conflict logic misfires.** Last-writer-wins needs a defensible order; client clocks skew. Use server-assigned ordering (Figma needs no timestamps because the centralized server defines event order) or hybrid logical clocks, never raw client time.
6. **Testing requires chaos, not just unit tests.** Replay real replication-lag distributions in integration tests: write, read immediately, assert the merge layer's behavior. Most optimistic-UI bugs only appear under specific interleavings.

## When (Not) To Apply

1. **Apply wherever users read what they just wrote.** Feeds, profile pages, settings screens, and admin consoles are the canonical cases; these are where stale reads become bug reports.
2. **Apply for collaborative and offline-capable products.** If the product promises multiplayer or offline editing, property-level conflict design, fractional ordering, and replay are mandatory, not optional polish.
3. **Skip when the operation is irreversible or high-stakes.** Payments, transfers, and deletions should confirm server-side before showing success; optimistic UI on irreversible actions converts a latency problem into a trust problem.
4. **Skip when you can afford read-your-writes at the storage layer.** If a strongly consistent read of the primary is cheap for the rare write-then-read path, just do that and keep the UX dumb — the overlay machinery is significant maintenance burden.
