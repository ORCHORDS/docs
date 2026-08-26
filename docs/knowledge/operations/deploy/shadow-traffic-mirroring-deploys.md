# shadow-traffic-mirroring-deploys

**Issue:** Canary releases expose a bad change to a small slice of real users before you know it is bad. Shadow deployments (traffic mirroring / dark launches) close that gap: a copy of live production traffic is replayed against the candidate version, responses are observed but discarded, and no user ever sees the candidate's output. Teams skip mirroring because it feels exotic, then ship a rewrite that passes staging but diverges from production behavior under real payload shapes and real volume. This article covers when mirroring is worth it and how to run it without duplicate emails, doubled database writes, or compliance surprises.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How mirroring differs from canary

1. **Responses are fire-and-forget.** In an Istio/Envoy mirror policy (VirtualService with the mirror and mirror_percentage fields), mirrored requests are sent asynchronously to the shadow service and their responses are dropped. The user only ever receives the production version's answer, so shadow latency and shadow errors never touch the user experience.
2. **100 percent coverage of zero users.** A 1 percent canary tests the change on 1 percent of users. A 10 percent mirror tests it against 10 percent of traffic while affecting zero users. The blast radius of a shadow failure is the shadow itself — it can crash-loop and production keeps running.
3. **It validates, it does not release.** Mirroring is a pre-release confidence stage, not a rollout strategy. Current guidance (Istio docs, Tetrate, OneUptime 2026) consistently frames it as something you do before or alongside canary, not instead of it — after mirroring says the candidate behaves, you still canary to expose it incrementally.
4. **It tests production truth.** Staging traffic is synthetic and polite; mirrored traffic carries the real malformed payloads, unusual locales, oversized headers, and timing distributions that break rewrites. InfoQ's microservices mirroring writeups center this: divergence found under mirrored load is divergence staging would never have found.

## Setting up a mirror safely

1. **Start at a low percentage.** Begin with 1-10 percent via mirror_percentage, verify the shadow pipeline end to end (request arrival, logging, metric emission), then ramp. Jumping straight to 100 percent mirror doubles downstream load instantly and can degrade the production path through shared resource contention.
2. **Never mirror non-idempotent side effects.** The top documented failure of shadow deployments: mirrored traffic triggers duplicate payments, duplicate emails, or double-written database rows. Restrict mirroring to read-only endpoints, or point the shadow at an isolated environment — a database copy or stubbed downstreams — so writes land somewhere disposable.
3. **Deduplicate or tag mirrored work.** If the shadow must touch shared systems, stamp every mirrored request with a header or attribute (for example an x-shadow: true marker propagated through context) and make downstream consumers drop or bucket it. Without propagation, a shadow call hopping to a second service silently becomes a real call.
4. **Size and monitor the shadow separately.** Mirroring adds CPU and memory load to the cluster and doubles per-percentage request volume to whatever the shadow touches. Give the shadow its own resource limits and watch its saturation; a shadow that throttles tells you nothing about production behavior at volume.
5. **Throttle and sample expensive paths.** Long-tail endpoints (reports, exports, LLM calls) can be mirrored at a lower percentage than cheap endpoints. Per-route mirror percentages keep cost proportional to information gained.

## What to compare

1. **Response diffs.** Record production and shadow responses side by side (schema-normalized, with PII scrubbed) and compute a divergence rate. A rewrite that differs on 0.01 percent of payloads tells you exactly which payload shapes need attention before the canary starts.
2. **Latency and error distributions.** Compare p50/p95/p99 and error classes between versions under identical traffic. This is the honest performance test — same load, same data, same moment — and catches regressions load tests miss because load tests rarely reproduce real traffic mix.
3. **Resource efficiency.** Mirror traffic exposes cost per request of the new version before it becomes the only version. If the candidate uses 3x the memory per request, you want to know while it is still discardable.
4. **Crash and hang behavior.** A shadow that accumulates leaked connections or slowly degrades over hours under continuous mirrored load reveals stability bugs that a 15-minute canary window will never see.

## Guardrails and limits

1. **PII and compliance review before mirroring.** Mirrored production traffic can contain personal data flowing into a new environment, new logs, and possibly a new region. Treat starting a mirror as a data-processing change: know what is captured, where it is stored, and retention. Redact or tokenize payloads where possible.
2. **Budget the cost explicitly.** Mirroring is paid confidence — compute for the shadow fleet, storage for comparison logs, downstream quota consumption. Set a maximum mirror percentage and a calendar end date so an emergency mirror from a stressful week does not silently run for months.
3. **Remember what a mirror cannot catch.** Mirrors only show request/response behavior. They miss client-side effects, timing-of-delivery effects, and anything depending on which version answered. Mirroring is one stage in the chain — shadow, then canary, then full rollout — not a replacement for the later stages.
