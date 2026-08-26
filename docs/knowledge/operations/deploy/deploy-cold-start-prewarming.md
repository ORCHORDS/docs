# deploy-cold-start-prewarming

**Issue:** A deploy can be fully "successful" and still deliver a terrible first two minutes. Every new instance, Lambda execution environment, or freshly rolled pod starts cold: JIT warmup, dependency loading, cache priming, and connection-pool establishment all happen on the first real request's time budget. Traffic immediately after a release therefore hits the new code at its slowest, which pollutes canary comparisons (the new version looks slower than it intrinsically is), trips latency alerts, and makes real users the warm-up load. Worse, in serverless platforms a deployment resets exactly the warmth the previous version had accumulated, so deploys are the guaranteed cold-start moment. Post-deploy warm-up treats this explicitly: prewarm instances before they take traffic, or make the warm-up phase a deliberate, measured part of the rollout, so deployment health and cold-start noise stop being confused.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why deploys are the worst-case cold start

1. **Fleet-wide warmth reset.** A rolling or blue-green deploy replaces every instance with one that has empty caches, uncompiled paths, and no established connections. Even a canary that is intrinsically faster will lose its first benchmarks to warm-up, because it is racing warm incumbents.

2. **Canary bias.** Progressive delivery compares new-version metrics against old-version metrics — but the old version is warm and the new version is cold. Without correcting for warmth, latency-based canary analysis produces false negatives (auto-rollback of a perfectly good release) or false positives (a genuinely slow release that improves as it warms).

3. **Alert pollution.** Latency and error-budget alerts that fire during the post-deploy warm-up window train the team to ignore alerts. Deployment windows should suppress or annotate expected warm-up latency rather than letting it masquerade as an incident.

## Serverless warm-up strategies

1. **Provisioned concurrency with scheduled scaling.** Pre-initialize a set of execution environments and keep them warm, scaling the provisioned level up ahead of known traffic peaks and down off-peak. This is the guaranteed option: the platform initializes environments after every deploy and before traffic arrives, at continuous cost.

2. **SnapStart where available.** SnapStart resumes functions from a pre-initialized snapshot, cutting initialization to near-instant for runtimes with slow inits (Java first, with other runtimes expanding coverage). It attacks init cost at its root instead of paying to keep environments idle, and pairs well with provisioned concurrency for latency-critical paths.

3. **Invoke the alias, never the unqualified ARN.** A classic trap: warm-up invocations or provisioned concurrency that seem ineffective because traffic invokes the unqualified function ARN, which always routes to an unprovisioned environment and cold-starts. Post-deploy warm-up must target the versioned alias (the same qualified ARN the live traffic uses), and note that after each deploy the provisioned environments re-initialize — the warm-up job belongs in the deploy pipeline, not on a cron.

4. **Scheduled pings are an anti-pattern beyond low traffic.** EventBridge-scheduled ping invocations keep only a few environments warm, stop working under real concurrency, and cost money around the clock. Pings are acceptable only for demonstrably low-traffic functions; anything latency-sensitive deserves provisioned concurrency or SnapStart.

## Warm-up in the rollout path

1. **Readiness gates that require a warm request.** Mark an instance ready only after it has served (or been probed with) at least one representative request that exercises initialization — a warmup endpoint that loads caches, opens connection pools, and compiles hot paths, invoked by the rollout controller before the instance joins the load balancer. Liveness alone proves the process exists, not that it is fast.

2. **Synthetic warm-up calls before traffic shift.** In the deploy pipeline, after new instances are up and before shifting user traffic, fire a burst of synthetic requests against the new version (through the same routing path production uses). The first real user then hits a warm path; the synthetics absorb the p99.

3. **Cache and pool priming jobs.** Where the dominant warm-up cost is data (populating local caches, JIT, connection pools, DNS), make priming an explicit post-deploy step — run the cache loader, warm the pool, then open traffic. This converts unpredictable first-request latency into a known, measured pipeline stage.

4. **Hold warmth during bake periods.** During canary bakes, keep sending the canary a minimum request floor so it stays warm and its metrics remain comparable. A canary receiving trickles of cold-start-weighted traffic tells you nothing about steady-state behavior.

## Measuring warm-up honestly

1. **Split cold and warm latency metrics.** Tag request latency by whether the serving instance was newly started, and report cold and warm percentiles separately. Averaging them hides both problems: genuinely slow cold starts and regressions in warm performance.

2. **Compare canary and baseline at equal warmth.** Either exclude the first N minutes of canary metrics from analysis, or warm both sides synthetically before comparing. Automated rollback logic keyed on latency must account for warmth, or it will roll back every Tuesday's deploy.

3. **Budget warm-up in rollout SLOs.** Define an acceptable warm-up duration (time from instance start to serving within SLO) and track it as a deploy metric. When that budget creeps up, it is an early warning that initialization work is accumulating in the request path — fix it before the next deploy makes it everyone's first impression.
