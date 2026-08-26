# thread-pool-exhaustion

**Issue:** Thread pool exhaustion is the failure mode where a small percentage of slow requests silently consumes every worker and turns a 5 percent degradation into a 100 percent outage. Workers held by blocked calls cannot serve new requests, queues grow, and the service appears completely dead while CPU sits near zero, which is exactly why responders misdiagnose it. Public writeups describe this death spiral directly: a modest set of 15-second calls starving all 200 workers until nothing responds, and a 2024 web-stack outage postmortem traced to database connection pool misconfiguration. .NET practitioners call the classic cause sync-over-async, and it presents as a pseudo-deadlock with low CPU rather than an overload.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What happened

1. **A downstream dependency slowed, not stopped.** An upstream search service went from 40 ms to 8-second responses during a cache rebuild. Nothing failed health checks because the dependency was technically still answering.

2. **Blocked workers accumulated linearly.** Each request to the degraded path held one worker thread for the full 8 seconds. At normal request rates, within two minutes all 200 workers were parked inside the same blocking call.

3. **The queue made it worse.** New requests, including ones for entirely healthy code paths, queued behind the blocked workers. Every endpoint on the shared process became unresponsive, so the blast radius was the whole service, not the slow feature.

4. **Low CPU misled the responders.** Everyone on the bridge assumed overload and scaled out. Adding instances helped for ten minutes, then the new nodes filled with blocked threads too. The actual fix was timing out the blocking call at 500 ms, which drained the pool in seconds.

## Why pools die quietly

1. **Bounded pool, unbounded blocking time.** Pool size N with average hold time T saturates at N/T requests per second. A pool of 200 workers holding 8-second calls saturates at 25 requests per second, which is trivial traffic. Nobody computes this arithmetic when the call is "usually fast."

2. **Sync-over-async is the classic trigger.** Calling blocking or async code synchronously inside request handling pins a thread per call. In .NET this shows up as thread pool starvation with near-zero CPU; the same shape exists in JVM blocking I/O on async stacks and in Node's libuv thread pool for filesystem and crypto calls.

3. **Connection pools are the hidden multiplier.** Application threads waiting on an exhausted database connection pool hold their worker while waiting, so a DB pool problem instantly becomes an application thread pool problem, as the April 2024 postmortem illustrated.

4. **Unbounded task queues convert exhaustion into memory exhaustion.** When the queue in front of the pool is unbounded, requests pile up holding memory and user-facing timeouts fire server-side work that nobody is waiting for anymore.

## Diagnosis

1. **Check CPU first.** Saturated CPU suggests genuine overload; near-idle CPU with hung requests suggests pool starvation. This one observation redirects the whole response.

2. **Expose pool gauges.** Active threads, queue depth, and pool size must be first-class metrics. During this incident neither was exported, so the team inferred starvation from thread dumps taken on a hunch.

3. **Take a thread dump immediately.** Hundreds of identical stack frames parked on the same socket read is the signature. Keep the dump command in the runbook because it is the fastest confirmation available mid-incident.

4. **Look for the slow dependency, not the broken one.** The triggering dependency rarely fails its health checks. Correlate the onset with p99 latency changes in every downstream call, not with error rates.

## Prevention

1. **Every blocking call gets a timeout shorter than the request budget.** If the caller times out at 10 seconds and the callee at 30, the caller's threads die waiting. Timeouts must be aligned inward-out, with the outermost budget the smallest.

2. **Bulkhead the risky paths.** Give calls to flaky or slow dependencies their own small, dedicated pool so one bad dependency cannot colonize the entire worker pool. This is the single highest-leverage structural fix.

3. **Never block on async frameworks.** The answer to sync-over-async is always to go fully async on that path, not to raise the pool size. Raising pool size just delays saturation and adds context-switch cost.

4. **Alert on queue depth, not just pool utilization.** Sustained nonzero queue growth at normal traffic is the early warning. Pool utilization of 100 percent means you are already late.

5. **Load test with slow dependencies injected.** Standard load tests use fast, healthy mocks. Fault-injection testing that delays one dependency by seconds exposes saturation arithmetic before customers do.
