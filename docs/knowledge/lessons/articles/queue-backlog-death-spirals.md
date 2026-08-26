# queue-backlog-death-spirals

**Issue:** A queue's consumers slow down for a routine reason — a deploy, a dependency blip, a burst of expensive messages — and never catch up. Backlog grows, consumer lag climbs, and the system enters a spiral: processing stale messages triggers downstream writes that now conflict or duplicate, retries re-enqueue work on top of the backlog, consumer batches grow until they hit memory limits and crash, and each crash loses prefetch and re-delivers everything. The AWS Builders' Library guidance on using queues to avoid cascading failures explicitly warns about this class — queues buffer bursts but convert sustained overload into a backlog that then amplifies load when drained. This is distinct from poison-message retry storms (one bad message looping) and from consumer idempotency bugs: the death spiral is a throughput and staleness failure where the queue's own backlog becomes the load generator.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The spiral mechanics

1. **Stale work is more expensive than fresh work.** Messages that waited in a backlog often reference state that has changed: caches they warmed expired, rows they update have moved, sessions ended. Processing aged messages triggers cache misses, lock contention, and retries at a higher rate than live traffic — so throughput per consumer drops precisely when the backlog demands more.
2. **Backlog generates its own traffic.** Every failure inside backlog processing re-enqueues (retries), every alert fires webhooks, every monitor polls harder. The system's input rate becomes a function of its output rate — the feedback loop that distinguishes a spiral from mere slowness.
3. **Consumers degrade under their own prefetch.** Kafka-style consumers fetch big batches to be efficient; when processing per message slows, batches pile up in memory, consumers exceed session timeouts, get kicked from the group, and trigger partition rebalances — which pause consumption for everyone. The group spends more time rebalancing than processing.
4. **Downstream saturates from catch-up.** When consumers do speed up (scaled out, batch mode), they now hammer downstream databases and APIs at multiples of normal rate — the drain phase can take out the very dependencies whose blip started the backlog. Catch-up without rate limiting is a self-inflicted attack.

## Detection before the spiral

1. **Monitor lag in time, not message count.** "Two million messages pending" is meaningless; "messages are being processed 40 minutes after enqueue and the gap is widening" is actionable. Consumer-lag tooling in the Burrow/Confluent tradition exists precisely because raw offsets mislead.
2. **Alert on the derivative.** A backlog that is growing faster than consumers drain it (negative drain rate) for more than a few minutes is the earliest reliable signal. Absolute lag thresholds page too late by construction.
3. **Track consumer group health separately from consumer process health.** Processes can be up while the group is rebalance-looping or processing at a fraction of capacity. Group-level metrics (commit rate, rebalance count) catch the spiral; process uptime does not.
4. **Instrument per-message processing time by age.** If old messages take 3x longer than fresh ones, your workload is spiral-prone by design and you should know that before an incident proves it.

## Breaking the spiral

1. **Shed or drop before you scale.** The fastest lever is usually reducing input: pause producers of non-critical topics, enable sampling, or drop low-value job types entirely (with a flag designed in advance). Scaling consumers into a spiral feeds it; shedding input starves it.
2. **Cap the drain rate.** Fix downstream rate below saturation, even if it means the backlog persists longer. A backlog that drains over six hours is survivable; a downstream database that dies during catch-up converts a delay into an outage.
3. **Skip or fast-fail stale work.** When draining, bypass messages whose work is now pointless — expired notifications, superseded updates, session-scoped events past their TTL. The pre-approved staleness policy must exist in the runbook, because deciding at 3am which messages "don't matter" never goes well.
4. **Fix the consumer, then rebalance deliberately.** Stop the group, deploy, and restart in a controlled fashion rather than letting timeout-driven rebalances thrash. Partitions should be stable before measuring whether throughput recovered.
5. **Quarantine failures instead of retrying inline.** Divert failing messages to a dead-letter path immediately during an incident; the backlog's job is to carry good work forward, and mixing retries into it obscures both.

## Design rules that prevent spirals

1. **Make consumers O(1) in message age.** Design handlers so processing cost is independent of how long the message waited — no exponential backoff-on-stale-state, no re-fetching the world per old message. If handlers must expire old work, make that the default path, not an incident-time decision.
2. **Bound retry counts and quarantine early.** Retries belong on a separate path with their own budget (distinct from the original backlog), so a message that fails three times exits the pipeline rather than re-entering it.
3. **Capacity-plan for drain, not just steady state.** Know your maximum safe drain multiple (e.g., "consumers can run at 3x normal rate without hurting the database") and encode it — autoscaling limits, downstream rate caps — so catch-up can never outrun the dependencies.
4. **Rehearse the drain.** Inject a synthetic multi-hour backlog in staging quarterly and measure real drain rate end to end. Every spiral incident reveals that the team's assumed drain throughput was theoretical.
