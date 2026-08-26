# long-lived-connection-rollout-draining

**Issue:** A rolling update assumes requests are short: kill the pod, in-flight work finishes in milliseconds, replacement serves the next request. WebSocket and SSE (server-sent events) connections break that assumption — a connection may legitimately live for hours or days, so "wait for in-flight requests to drain" either hangs the rollout or, more commonly, someone sets the grace period too low, the pod is SIGKILLed, and thousands of clients discover the death via timeout simultaneously. Every client then reconnects at once: the reconnect stampede, which 2025-2026 practitioner discussions (r/node, DevOps StackExchange, dedicated reconnection-storm writeups) describe as the most underestimated deploy failure mode in event-driven systems. Deploying connection-holding services safely requires server-side draining and client-side backoff designed together.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why normal rolling updates break

1. **Drain never completes.** terminationGracePeriodSeconds waits for in-flight work, but an SSE stream that runs for hours is always in-flight. The pod either blocks the rollout until timeout or gets hard-killed mid-stream. The graceful-shutdown basics in graceful-shutdown-patterns.md cover SIGTERM handling generally; long-lived connections need an active eviction protocol on top.
2. **Timeouts are the worst notification.** A client that learns of server death by TCP timeout waits out its timeout, reconnects blind, and cannot distinguish server replacement from server outage — so monitoring screams outage on every deploy, drowning real signals.
3. **Kills synchronize reconnection.** If a rolling update terminates 20 pods over 10 minutes and each held 5,000 connections, 100,000 clients reconnect in waves sized exactly like your batches. Reconnect handling — auth, state resync, subscription replay — costs multiples of steady-state request cost, so the spike lands on both the new pods and every downstream dependency they call during resync.

## Server-side draining protocol

1. **Announce, then close.** On SIGTERM, send an application-level going-away message (a WebSocket close frame with a meaningful code, or an SSE event like event: shutdown) before closing. The client learns instantly, deliberately reconnects, and can skip its timeout period. Client libraries differ — check your WS library's shutdown API, since some require explicit close calls the runtime will not do for you.
2. **Stop accepting, then evict gradually.** Deregister from the load balancer or remove the pod from the Service endpoints first, let a preStop hook sleep briefly so LB health checks converge, then close live connections in small staggered batches rather than all at once. Draining in batches is the server-side half of stampede prevention (the drain-vs-kill comparison in current rolling-update guides recommends exactly this).
3. **Give sessions a resumption path.** Before closing, hand the client a session or cursor token (last event id, subscription state) so reconnection is a cheap resume rather than full re-subscribe. State sync after reconnect is the hard part — the transport reconnect is trivial by comparison, as reconnection guides from websocket.org emphasize.
4. **Bound the drain, plan for the stragglers.** Set terminationGracePeriodSeconds to your acceptable eviction horizon and accept that some clients will be dropped hard at the deadline. Better a controlled batch of hard drops at a time you chose than an accidental SIGKILL of everything.
5. **Respect PodDisruptionBudgets.** For connection-holding services, minAvailable matters as much as for stateful ones: PDBs and the Deployment's rolling-update policy are enforced independently (a subtlety surfaced in 2026 Kubernetes lifecycle writeups), so verify both allow one pod's worth of connections to drain at a time.

## Client-side stampede defense

1. **Exponential backoff with full jitter.** Reconnect delay grows with consecutive failures and is randomized across clients — jittered backoff (for example a random slice of 50-500ms at the base) is the single highest-leverage defense, because it de-synchronizes a herd that the deploy synchronized. Never use fixed-interval reconnects in clients that will exist in the thousands.
2. **Respect the server's hints.** If the going-away message carries a retry-after, honor it. The server knows how many peers are being evicted in this batch and can spread reconnection across the drain window better than any blind client policy.
3. **Reconnect to the new version, not just any version.** During a slow rollout, a reconnect may land back on an old-version pod. Ensure subscription/resume payloads tolerate either version, or clients will resync into a pod that cannot answer them (see event-schema-compat-deploys.md for payload compatibility rules during mixed-version windows).
4. **Make resync idempotent and bounded.** A client that re-subscribes on every reconnect attempt amplifies load multiplicatively. Cap retry state, deduplicate subscriptions, and cache resume tokens so a flapping network does not turn each client into a subscription storm of its own.

## Deploy-time engineering

1. **Stagger batches below the reconnect budget.** Measure what reconnection burst the new pods plus dependencies can absorb (auth rate limits especially), then cap the rolling update so simultaneous evictions stay under it — smaller maxUnavailable and longer batch spacing beat a fast rollout that triggers its own outage.
2. **Throttle new connections during the window.** Accepting reconnects at full rate during drain lets the herd stampede the shrinking old pods' replacements; a modest admission throttle (or LB connection queue) smooths the surge at the cost of seconds of reconnect latency, which clients' backoff already tolerates.
3. **Instrument the mixed-version window.** Track reconnect rate, resync duration, and resume-failure rate per pod version during rollout. A deploy that quadruples reconnect duration without failing any health check is still a regression your latency metrics must catch (post-deploy-monitoring-checklist.md).
4. **Drain outside peak hours until proven.** Until several rollouts show stampede metrics stay flat, treat connection-heavy deploys like the risk class they are and schedule them when a reconnect wave is cheap (deployment-window-management.md). After metrics prove calm at 5 percent batches, ramp batch size with evidence, not confidence.
