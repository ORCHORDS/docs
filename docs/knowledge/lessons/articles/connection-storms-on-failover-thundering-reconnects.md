# connection-storms-on-failover-thundering-reconnects

**Issue:** Every failover, deploy, or network blip simultaneously disconnects the entire client population — and if those clients reconnect on their own schedule, they do it in a synchronized wave that kills whatever infrastructure survived the original failure. A stateful server crash drops 33,000 WebSocket clients at once; they all retry, overwhelm the surviving nodes with TCP handshakes, TLS negotiation, and authentication work, and the secondary failure becomes worse than the primary. The same dynamic hits mobile fleets when a carrier recovers, load balancer pools during rolling deploys, and database clusters during failover when hundreds of app instances re-establish pools in lockstep. The core insight from the 2025-2026 writeups: thundering herds are a problem of *synchronized* traffic, not high traffic — total load may be modest, but its alignment in time exceeds what any real-time provisioning can absorb.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why reconnects are so expensive

1. **A reconnect is not cheap; it is the most expensive request a client makes.** TCP handshake, TLS negotiation, auth token validation, session-state rehydration, and subscription replay all happen before any useful work. Multiply by tens of thousands of synchronized clients and the surviving servers spend 100% of CPU on ceremony with zero capacity left for traffic.
2. **Clients synchronize without meaning to.** Fixed-interval retry timers, identical backoff constants, and aligned polling schedules mean clients that disconnected together will retry together, forever. Without deliberate randomization, the herd re-forms on every retry cycle.
3. **Health checks make recovery self-defeating.** If a server marks itself healthy while still draining its reconnect backlog, the load balancer routes it more traffic, which lengthens the backlog, which delays real recovery — a feedback loop that turns a 30-second blip into a 20-minute outage.
4. **Mobile fleets amplify the wave.** When a carrier tower or regional network recovers, every affected device retries at once, often through fallback transports (long-polling after WebSocket failure), multiplying request volume per device exactly when capacity is most fragile.

## Designing reconnects that cannot stampede

1. **Exponential backoff with full jitter, always.** Backoff alone is not enough — deterministic backoff keeps the herd synchronized at larger intervals. Full jitter (uniformly random delay in `[0, min(maxDelay, base * 2^attempt)]`) decorrelates clients and is the single highest-leverage line of code in any reconnect path (the AWS exponential-backoff-and-jitter pattern remains the reference).
2. **Server-side jittered draining on deploy and failover.** When taking nodes out of rotation, stop accepting new connections and send close frames with randomized retry-after hints so clients reconnect in a staggered fashion over tens of seconds, rather than all in the next 100ms. Graceful drain is a protocol feature, not an ops nicety.
3. **Retry-After headers turn dumb clients into polite ones.** A recovering or degraded server that tells clients when to come back — with per-server randomization — converts an uncontrolled wave into a scheduled ramp. Honour it client-side, and make degraded responses carry it too (429/503), not just successes.
4. **Single-flight reconnection in process.** Within one client (browser tab, app instance, SDK), collapse concurrent reconnect attempts from multiple subsystems into one connection establishment. Ten SDKs each opening their own socket multiplies the storm by ten.
5. **Cap the reconnect rate in the client, not just the server.** A client-side token bucket on reconnection attempts (e.g., at most one attempt per N seconds regardless of internal state changes) is the only protection that works when the server is too overloaded to enforce anything.

## Server-side defenses

1. **Admission control at the front door.** Limit concurrent handshakes (TLS in-progress, auth in-progress) and queue or reject the excess with jittered Retry-After rather than letting the handshake path consume all memory and CPU. A connection queue that sheds load during the storm lets the system recover instead of thrash.
2. **Warm the cache of nothing: degrade auth during storms.** If every reconnect re-validates tokens against a downstream auth service, the storm cascades to that service. Short-TTL local token verification or a cached-claims path keeps the wave from propagating deeper into the stack.
3. **Deprioritize reconnection work versus in-flight traffic.** Request schedulers that class handshake/auth work below active-session requests mean existing users keep working while reconnecters wait — the outage shrinks from "everyone" to "the reconnecting cohort, gradually."
4. **Watch the metric that predicts the storm.** Alert on connection-establishment rate (handshakes/sec, new-sessions/sec) and on LB queue depth, not just steady-state RPS. The storm is visible 30+ seconds before saturation if you instrument the right counter.

## Operational discipline

1. **Test failover under a reconnect storm, not just steady state.** Chaos exercises that drop a node while a realistic client population is connected are the only honest test of backoff behavior — most teams test the failover mechanics and never test the reconnect wave they trigger.
2. **Roll deploys in small waves with drain gaps.** Taking 25% of capacity out at once guarantees the reconnect wave exceeds the remaining 75%; draining one node fully (with jittered close frames) before touching the next keeps the wave below the waterline.
3. **Respect circuit breakers on the client too.** Client-side circuit breakers that stop attempting reconnection entirely for a cool-down period after repeated failure prevent zombie clients from generating load that serves no one — especially fleets of mobile devices with stale sessions.
4. **Budget the handshake headroom.** Capacity plans that assume 100% of connections are steady-state are wrong for any system that fails over. Provision (or autoscale triggers set) for re-establishing a large fraction of all connections within a few minutes — the storm is a planned event in any HA design.
