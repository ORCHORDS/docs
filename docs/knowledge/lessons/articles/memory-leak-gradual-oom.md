# memory-leak-gradual-oom

**Issue:** A slow memory leak is the most patient killer in production. Unlike a crash or a bad deploy, it gives no single dramatic moment: latency creeps up over days, GC pauses lengthen, and then one morning the process is OOM-killed at peak traffic. Because deploys and restarts recycle memory, the leak is masked for weeks, and teams normalize the degradation ("it always gets slow before the nightly restart"). Real incidents back this pattern: Honeycomb published an incident report titled "Running Dry on Memory Without Noticing" where a leak introduced by one commit went undetected until it was severe, and Cloudflare's June 27, 2019 outage involved a memory leak that had coexisted with the rules engine for years before a second change turned it fatal across roughly 80 percent of their edge network.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What happened

1. **The deploy was green.** A routine release added a caching layer to a hot path. Nothing failed at deploy time, load tests passed, and memory looked normal for the first 24 hours because the leak only accumulated under production traffic shapes that tests never reproduce.

2. **Restart cadence hid the disease.** The service restarted every few days for unrelated deploys, resetting memory to baseline. The leak was therefore invisible on any dashboard with a short window. By the time deploys became less frequent, resident memory was climbing from 30 percent to 90 percent of the container limit over five days.

3. **The crash came at the worst time.** At peak traffic the kernel OOM-killed the largest pods first. The orchestrator restarted them, they rejoined the cluster cold, drew traffic, absorbed a burst of in-flight requests, and were killed again. This kill-restart loop converted a degradation into a full outage lasting 40 minutes.

4. **The fix was a revert, but finding it took hours.** Nobody suspected the release from ten days earlier. Bisecting memory growth across deploys required heap dumps and per-version memory telemetry that did not exist yet. The Honeycomb incident followed the same shape: the eventual fix was reverting the offending commit, but identifying the commit was the expensive part.

## Why leaks evade detection

1. **Dashboards show utilization, not trajectory.** A gauge reading "65 percent memory used" looks healthy at 9 a.m. and is meaningless without the slope. What matters is bytes-per-hour growth under steady traffic, and almost no default dashboard plots it.

2. **Deploys are accidental memory resets.** Any team shipping daily is unknowingly running a memory leak bleach cycle. The leak only surfaces during a deploy freeze, a holiday week, or when a long-lived connection pool finally accumulates enough to hit the limit.

3. **OOM kills look like infra flakiness.** An OOMKilled exit code on one pod gets treated as a node hiccup. Without an alert specifically on OOM-kill events, the kill-restart loop at peak is diagnosed as "Kubernetes being weird" while the real cause is trajectory, not state.

4. **GC languages fail indirectly first.** On the JVM or in Go, the leak often manifests as rising GC pressure: p99 latency climbs long before the process dies. Teams chase the latency symptom, add instances, and delay the heap analysis that would have found the root cause.

## Detection and defense

1. **Alert on slope, not threshold.** Track memory growth rate under steady-state traffic and alert when a pod's resident memory exceeds a projected time-to-limit of less than seven days. A fixed 85 percent alarm fires too late to plan around.

2. **Run a soak test before weekly releases.** Replay a representative traffic profile against a single instance for 48 to 72 hours with no restarts and chart memory. A leak that adds 50 MB per hour is invisible in an hour-long load test and obvious in two days.

3. **Bisect by deploy marker.** Emit the build version as a metric label and overlay per-version memory curves on one chart. The version whose curve bends upward is the culprit. This turns hours of heap-dump archaeology into a five-minute chart read.

4. **Make OOM kills loud.** Alert on any OOMKilled event in any namespace, even one. It is always a real defect even when it is survivable, and it is the earliest unambiguous signal that a leak has crossed into fatal territory.

## Recovery lessons

1. **Restart is a valid mitigation, not a fix.** A coordinated rolling restart buys hours of headroom while the offending deploy is found. Do it immediately and in parallel with diagnosis, not after.

2. **Take the heap dump before restarting.** The dying process holds the evidence. One command capturing a heap dump at 90 percent memory, kept on a warm path in the runbook, is the difference between a same-day fix and a multi-day mystery.

3. **Cap memory at the container level deliberately.** A hard limit converts a slow leak into a crash-loop; that is still usually the right call because it makes the failure explicit, but only if OOM alerts exist. An uncapped process instead degrades the whole node and takes neighbors down with it.
