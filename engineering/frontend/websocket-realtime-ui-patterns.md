# websocket-realtime-ui-patterns

**Issue:** A realtime UI (live dashboards, collaboration, chat, market data) needs far more than opening a WebSocket: connections die silently behind proxies, mobile networks flap, messages arrive out of order or duplicated after reconnects, and a naive client renders a mixture of stale and fresh state that users cannot trust. WebSockets give no auto-reconnect, no heartbeat, no delivery guarantees, and no state resumption — all of that is client engineering. Current practice (2025-2026 guides from Ably, websocket.org, and production React writeups) converges on a layered architecture: a connection layer owning socket lifecycle and heartbeats, a protocol layer owning ordering/deduplication/resumption, and a state layer merging messages into queryable state — with exponential backoff plus jitter for reconnection and honest connection-state UX. Deciding WebSocket versus SSE versus polling is itself part of the design: most realtime UIs are one-way, where SSE's free reconnection is the cheaper choice.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Choosing the transport

1. **SSE for one-way updates.** If the server only pushes (dashboards, feeds, notifications), Server-Sent Events reconnects automatically with a Last-Event-ID header and works over plain HTTP infrastructure — 2025 comparisons consistently recommend it before WebSockets for read-mostly UIs.
2. **WebSocket for bidirectional or low-latency needs.** Use WebSockets when the client sends high-frequency messages (presence, typing, cursor movement, multiplayer) or needs a single persistent low-latency channel in both directions.
3. **Polling as the fallback tier.** Long or short polling remains a legitimate degradation path for hostile networks (corporate proxies, some mobile carriers) and a circuit-breaker state when the realtime endpoint is failing — design the state layer so the transport is swappable underneath it.
4. **One socket per app, multiplexed.** Multiple components each opening their own socket exhausts connections and mobile battery; run a single connection with topic/channel subscription semantics, and refcount subscriptions so the socket closes when nothing needs it.

## Connection lifecycle management

1. **Heartbeat/ping-pong to detect dead peers.** A TCP connection can look open while the peer or an intermediary is gone. Send application-level pings on an interval (and expect pongs within a timeout) because browser WebSocket clients cannot send protocol-level pings on demand — a missed pong must trigger teardown and reconnect.
2. **Exponential backoff with jitter.** Reconnect after 1s, 2s, 4s... capped (e.g., 30s), with random jitter so a fleet of clients that dropped together (deploy, network blip) does not stampede the server in lockstep — the classic thundering-herd failure.
3. **Respect page visibility.** On mobile, pause or thin out heartbeats when the tab is hidden and do a full state resync when it becomes visible again; a socket that "survived" backgrounding often delivers a silently stale view.
4. **Model connection state explicitly.** Track a small state machine (connecting, open, reconnecting, degraded, closed) and expose it to the UI — connection quality is part of the product surface, not an implementation detail.
5. **Authenticate and re-authenticate.** Attach short-lived tokens on connect (query or first message), and handle the reconnect path re-fetching fresh tokens; expired-token reconnect loops are a common silent outage.

## Layered client architecture

1. **Connection layer.** Owns the socket: open/close, heartbeats, backoff, subscription refcounts, and emitting normalized events. Knows nothing about application state. In React apps this is a singleton (module or context), never per-component.
2. **Protocol/session layer.** Owns message semantics: sequence numbers, acknowledgements, dedupe, ordering, resumption cursors, and translating transport events into state-layer operations the UI can apply blindly.
3. **State layer.** Applies validated messages into the same store used by REST (query-cache style), so realtime updates and refetched data flow through one merge path — two divergent paths is how screens disagree with themselves.
4. **UI layer with hooks.** Components subscribe through small hooks (useChannel, useLiveQuery) that express what they need, not how transport works; the hook returns data plus live/freshness status so components can render staleness honestly.

## Message semantics and state synchronization

1. **Sequence numbers for ordering and dedupe.** Have the server stamp per-stream monotonically increasing sequence IDs; the client drops already-seen sequences, buffers gaps, and requests the missing range — this is what makes "reconnect without duplicates or holes" possible.
2. **Resumption cursors on reconnect.** After a reconnect, send the last received sequence/cursor (or a session ID) so the server replays the gap; when the gap is too old, fall back to a full snapshot refetch rather than an inconsistent partial replay.
3. **Prefer snapshot-plus-delta for dashboards.** On subscribe, the server sends a full snapshot then deltas keyed to the snapshot version; the client applies deltas only against the matching version and re-snapshots on any mismatch or reconnect.
4. **Idempotent mutations.** If the client also sends changes, attach client-generated IDs so retries after a dropped connection (the ack never arrived) do not double-apply — the server dedupes on the ID.
5. **Backpressure on the client.** A burst of thousands of messages must not trigger thousands of renders: batch/coalesce messages per animation frame (or 50-100ms window), and for high-frequency streams (ticks, cursors) keep only the latest value per key.

## UX for connection states and failures

1. **Render liveness, not false freshness.** Show a subtle "live/stale/reconnecting" indicator with a last-updated timestamp; users forgive a stale dashboard they can see is stale and punish one that looks live but is frozen.
2. **Degrade gracefully to fetched data.** When realtime is unavailable, the UI must still work from REST data with a manual or timed refresh — realtime is an enhancement, never the only data path.
3. **Optimistic UI stays separate.** Local optimistic changes (see optimistic-update patterns) must reconcile against the authoritative stream on reconnect; order reconciliation by server sequence, not arrival.
4. **Queue or reject user actions while disconnected.** For collaboration-type apps, queue outbound edits with IDs and replay them on reconnect; for command apps, disable destructive actions and say why — a greyed-out button beats a silently dropped action.
5. **Instrument the connection in production.** Log reconnect counts, gap-recovery frequency, heartbeat timeouts, and time-to-first-message; fleets of silently reconnecting clients are invisible until users report "the numbers look wrong", and by then trust is gone.
