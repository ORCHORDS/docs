# cache-cold-start-avalanche

**Issue:** A cache that quietly absorbs 95 percent of database load hides the true query cost of the system. The moment that cache restarts empty, fails, or is flushed, every request becomes a cache miss simultaneously, and the full unprotected query volume lands on a database that was sized for 5 percent of it. Redis's own engineering blog describes this thundering herd as an avalanche of cache misses when keys expire together or a cache restarts empty, and practitioner writeups have measured database load spiking by an order of magnitude within milliseconds of invalidation events. The defining cruelty is that recovery actions make it worse: restarting the database or the cache resets the warm state and restarts the avalanche.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What happened

1. **A routine maintenance restart emptied Redis.** The cache cluster was restarted to apply a config change. The runbook said "restart Redis" and nothing else, because previous restarts had happened at 3 a.m. when traffic was 4 percent of peak.

2. **Every hot key missed at once.** Within two seconds of the cache coming back, thousands of concurrent requests found no entries and each issued its own database query. The read path had no request coalescing, so the fan-out was one-to-one.

3. **The database fell over and reset the clock.** Connection counts exploded, the database saturated, queries stacked up, and the health-checking layer began timing out. Operators restarted the database to clear the backlog, which dropped its buffer pool warmth and guaranteed the second wave was just as bad.

4. **Retries stacked a second avalanche on the first.** Application retries with short backoff re-issued misses while the first wave was still executing. Load on the database peaked at roughly 15 times its steady-state ceiling.

5. **The system never recovered until traffic was shed externally.** The loop broke only when the team put a serve-stale static fallback page in front of the API and let the cache warm at a survivable rate, taking 25 minutes of degraded service.

## The avalanche mechanism

1. **Hit rate hides query volume.** At 97 percent hit rate, the database sees 3 percent of logical reads. Nobody provisions a database for 100 percent, so the cold cache demands 33x its normal capacity. The cache is load-bearing infrastructure, not an optimization.

2. **Expiry synchronization manufactures cold starts.** Keys written at deploy time with identical TTLs expire together, producing the same miss storm without any restart. Bulk loads and bulk invalidations share this failure shape.

3. **Recovery actions re-trigger the failure.** Restarting the cache, the database, or the app tier all destroy warm state. During an incident, the instinct to restart everything is exactly wrong for this failure class.

4. **Timeouts convert misses into multiplier load.** When the database slows, requests time out and retry as new misses. Retry logic tuned for transient errors becomes an amplifier during a stampede.

## Mitigations that work

1. **Request coalescing on the read path.** Only one in-flight fetch per key should hit the database; concurrent requests for the same key wait on that fetch. Facebook's engineering team described solving exactly this for live video with request queues at the edge cache so a single request goes to origin per key. Libraries call this request collapsing, single-flight, or stale-while-revalidate locks.

2. **Probabilistic early expiration.** Refresh hot keys slightly before TTL with randomized jitter, so expiry is spread across time instead of synchronized. Combined with TTL jitter on writes, this removes the manufactured cold start.

3. **Warm the cache before admitting traffic.** After a restart, pre-populate the top N keys from a warmed snapshot or replay before opening the load balancer to full traffic. A 30-second warmup phase trades a slightly slower recovery for a survivable one.

4. **Shed load at the front door during warmup.** Serve stale data, serve cached static fallbacks, or queue arrivals. The one fatal choice is forwarding full traffic at an empty cache.

5. **Cap database concurrency independent of demand.** A connection limit and admission control at the database tier turns a would-be avalanche into a bounded queue, keeping the database alive long enough for the cache to warm.

## Monitoring

1. **Track cache-miss latency and miss rate separately.** Hit rate alone can look stable while miss latency, which is what the database experiences, spikes by an order of magnitude. Practitioner guidance is unambiguous that stampedes show up as miss-latency spikes first.

2. **Load-test the cold cache.** Every disaster-recovery drill should include "flush the cache at peak-equivalent traffic" as a scenario. A system that cannot survive a cache flush at 50 percent of peak is one maintenance restart away from this incident.

3. **Alert on simultaneous miss bursts.** A sharp rise in concurrent misses for distinct keys within a short window is the signature of expiry synchronization or cache restart, minutes before the database alerts fire.
