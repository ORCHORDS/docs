# Durable Object Hibernation WebSocket Budget

A Durable Object holding open WebSocket connections normally stays in memory for the lifetime of those connections, which means a chatty-but-idle fleet of connections bills duration-seconds continuously. WebSocket hibernation inverts that: the Object accepts connections through the Hibernation API, and when a client goes quiet, the runtime evicts the running instance while the connection stays logically open; an incoming message rehydrates the Object on demand. The budget question is which API to use for a given connection population, and what the cost and memory profile of each choice actually is. This article frames that decision with concrete sizing steps and the controls that keep a hibernation migration honest.

## Scope

Applies to Durable Objects serving WebSocket connections where connection counts, idle ratios, or message rates make the standard API's always-resident model a cost or memory concern. Covers API selection, capacity budgeting, and migration from the standard WebSocket API to the Hibernation API. Excludes server-sent events over plain fetch, plain room-style broadcast patterns with no idle tolerance, and non-WebSocket Durable Object workloads.

## Workflow or implementation guidance

1. Profile the connection population: peak concurrent connections, average session duration, share of time a typical connection is idle, and messages per connection per hour. These four numbers drive everything else.
2. Classify connections into hibernation-suitable and hibernation-hostile groups. Long-idle, event-driven connections (notifications, presence, feeds) suit hibernation; tight-loop streams with sub-second messages rarely hibernate and gain little.
3. Estimate the two budgets. Under the standard API, the Object is resident for the whole session, so billable duration tracks wall-clock connection time. Under the Hibernation API, duration accrues only while the Object is awake: during active message exchange and the brief wake windows for quiet connections.
4. Convert the estimate into a decision rule, for example: if idle time exceeds roughly half of connection lifetime across the fleet, hibernation is a candidate; below that, the wake-overhead per message can erase savings.
5. Implement with `acceptWebSocket()` in place of `accept()`, and move per-connection state into serializers (`serializeAttachment`/`deserializeAttachment`) because in-memory state does not survive eviction.
6. Handle the lifecycle hooks that replace manual bookkeeping: `webSocketMessage`, `webSocketClose`, and `webSocketError` receive events even when the Object was asleep at the moment the message arrived.
7. Run a dual-run comparison in a staging environment with representative idle patterns, then migrate one connection class at a time, watching wake latency and error rates per class.

## Controls

- Hibernation-suitability gate: a written profile (concurrent connections, idle share, message rate) must precede the choice of API; defaulting to hibernation without profiling is blocked.
- Attachment-state audit: no connection-critical state may live only in instance memory; it must round-trip through serializers or external storage.
- Wake-latency budget: a defined ceiling on rehydration delay observed by clients, verified during rollout, because hibernation trades residency for wake time.
- Lifecycle-handler coverage check: message, close, and error paths all implemented and tested, since unhandled events during sleep are a common migration defect.
- Per-class rollout cap: only one connection class migrates per change window, with its own metrics slice.
- Periodic re-profiling: idle ratios drift as clients change; the budget decision is revisited when the population profile shifts materially.

## Validation evidence

- Connection profile report (concurrent connections, session duration distribution, idle fraction, message frequency) that justified the API choice.
- Staging comparison output showing resident duration versus awake duration for an identical traffic replay.
- Serializer round-trip test results demonstrating state survives eviction and rehydration.
- Lifecycle handler test matrix covering message, close, and error events arriving while hibernating.
- Rollout metrics per migrated class: message error rate, close anomaly rate, wake latency percentiles.
- Billing-relevant before/after duration figures for the migrated class over equal-length windows.

## Failure modes and correction

- Heavy attachment serialization on every message: storing large blobs in attachments makes each message pay a serialization tax. Correct by moving bulky state to external storage and keeping attachments small.
- Connections never actually hibernate because a timer or interval keeps the Object awake: audit for lingering alarms or recurring wake sources and replace polling with alarms scheduled only when needed.
- Wake latency breaches the budget under load: reduce per-wake initialization work, or reclassify that connection class back to the standard API.
- Lost in-memory state after eviction causes protocol errors: any state read on message arrival must be reconstructed from attachments or storage inside the wake path.
- Errors thrown inside `webSocketMessage` silently kill quiet connections: add explicit error handling in the handler and alert on close anomalies during rollout.
- Broadcast patterns that must touch every connection wake the whole fleet: batch or coalesce broadcasts, or accept that highly interactive rooms belong on the standard API.

## Limitations

- Hibernation only helps connections with meaningful idle time; continuously active sessions see no benefit and may see slight overhead.
- The runtime decides when to evict; there is no manual "hibernate now" guarantee, so budget models are probabilistic estimates.
- Instance memory is not preserved across hibernation by design, which constrains designs relying on long-lived in-process caches.
- Subprotocol-specific compression or per-connection background processing may conflict with eviction behavior and needs case-by-case testing.
- Cost comparisons depend on plan-specific pricing dimensions; re-verify the arithmetic against the current pricing documentation before committing.

## Canonical sources

- Cloudflare Durable Objects docs, "Use WebSockets" (Hibernation API and Web Standard API): https://developers.cloudflare.com/durable-objects/best-practices/websockets/
- Cloudflare Durable Objects docs, "Pricing": https://developers.cloudflare.com/durable-objects/platform/pricing/
