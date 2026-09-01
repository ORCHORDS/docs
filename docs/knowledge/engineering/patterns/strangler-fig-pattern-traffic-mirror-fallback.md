# Strangler Fig Pattern Traffic Mirror Fallback

## Scope

This article covers the Strangler Fig application-migration pattern with two production safety mechanisms layered onto it: traffic mirroring to validate the replacement before it serves customers, and fallback routing to return traffic to the legacy system when the replacement misbehaves. Scope covers the incremental routing facade, shadow/mirror traffic mechanics and diffing, progressive cutover with fallback thresholds, and the dismantling of both the legacy system and the scaffolding. It assumes a live system with real traffic that cannot simply be stopped and rewritten; it excludes greenfield development, data-only migrations without routing changes, and parallel-run strategies where operators compare batch outputs rather than live traffic.

## Workflow or implementation guidance

Stand up the routing facade first, before any replacement code exists. The facade intercepts requests for the routes slated for replacement and initially forwards all of them to the legacy system unchanged. This step alone is a meaningful milestone: it establishes the interception point, proves the facade's latency and availability budget, and lets every later stage route by configuration rather than by deployment. Route by route — never all at once — and prefer routes that are self-contained, observable in outcome, and cheap to compare.

Then add mirroring for a route before serving from the replacement. The facade sends production requests to both systems, serves the legacy response to the customer, and asynchronously records the replacement's response for offline diffing. Mirroring mechanics matter: the mirrored call must be fire-and-forget on the customer path (never add its latency to user requests), duplicate writes and other non-idempotent side effects must be suppressed or sandboxed (mirror to an isolated environment where the replacement's writes land in a comparison store rather than the real one), and the mirror rate should be ramped — one percent, then ten, then full — so unexpected mirror load on shared dependencies is discovered early.

The diffing loop is the pattern's engine. Compare status, headers of consequence, and normalized bodies (whitespace, ordering, dynamic fields accounted for explicitly), classify every mismatch as replacement-bug, legacy-bug, or acceptable-difference, and drive the replacement's bug list to zero on each route before it serves traffic. Only then flip the route: a small percentage of live traffic served by the replacement, with the rest still on legacy.

Fallback is the cutover's safety net and must be automatic, not a runbook step:

```ts
async function route(req: Request): Promise<Response> {
  if (shouldServeNew(req)) {
    const res = await withTimeout(NEW.fetch(req), NEW_TIMEOUT_MS);
    if (res && !res.ok && res.status >= 500) {
      metrics.increment('fallback', { route: routeOf(req) });
      return LEGACY.fetch(req);            // customer sees legacy behavior, not an error
    }
    return res ?? LEGACY.fetch(req);
  }
  return LEGACY.fetch(req);
}
```

Define in advance which signals trigger fallback — 5xx rate, latency breach, exception rate, explicit kill switch — and at what thresholds, because the moment to design the escape hatch is before you need it. Serve a mixed population consistently per user or session where the replacement has user-visible state differences, so customers do not see behavior flicker between systems on consecutive requests.

Finish by dismantling deliberately: route at 100 percent on the replacement, keep mirroring off, keep the facade, and delete the legacy route handlers on a schedule — the fig has strangled the tree only when the legacy code is gone, and half-completed migrations that stop at 100 percent routing leave two systems to maintain forever.

## Controls

Gate every routing-percentage increase on explicit metrics: replacement error rate, latency against the legacy baseline, and business-level guardrails (order completion, payment success) per migrated route, with the thresholds written into the migration plan before the first flip. Keep the kill switch tested: flip a route fully back to legacy in staging on a schedule and once in production early — when traffic is low — so the mechanism is proven before it carries an emergency. Control mirror blast radius: mirrored writes must never touch production data stores, enforced by binding-level isolation between the mirror environment and real resources, reviewed as part of the mirror configuration. Track mismatch debt as an explicit backlog with a burn-down per route; a route whose acceptable-difference list keeps growing is a signal the two systems' semantics genuinely diverged and the comparison needs re-scoping. Time-box the whole migration: a strangler effort with no end state calcifies into permanent dual-running, so each route carries a target cutover date and the program has a defined dismantling milestone with the legacy system's decommission date.

## Validation evidence

Mirror-phase evidence is the core artifact: per route, the diff report over a representative traffic window — total mirrored requests, mismatch count, and the classification of every mismatch with a disposition (fixed, accepted, legacy-bug-workaround). A route is eligible for cutover only when unresolved replacement-bugs reach zero over a sustained window, and the eligible window length should scale with traffic volume. Fallback evidence: inject replacement failure modes (5xx storm, latency breach, hard timeout) in staging and assert the fallback path serves legacy responses within its latency budget, counters increment, and no customer-visible error escapes; repeat the drill in production during the low-traffic period after first flip. Consistency evidence: for a sampled user population, assert session-sticky routing kept each user on one system per session, since flicker is a user-experience defect invisible to aggregate metrics. Cutover evidence: per ramp step, the guarded metrics' actual values against the pre-agreed thresholds with the proceed/hold/rollback decision recorded. Post-cutover evidence: after 100 percent routing, a defined soak period's metrics matching or beating the legacy baseline, and the legacy decommission diff — the final proof the pattern completed rather than paused.

## Failure modes and correction

The most common failure is the eternal dual-run: routing reaches a comfortable percentage, organizational attention moves on, and both systems remain live for years with the facade permanently routing between them — all of the cost of migration and none of the benefit. Correct with hard decommission dates and dismantling treated as a milestone with an owner, not as cleanup that happens eventually. The second is poisoned mirroring: mirrored traffic executes writes against production stores, corrupting data from a system customers never saw. Correct with binding-level isolation of the mirror environment and a review gate on every mirror configuration change. A third is fallback discovered broken during the emergency: the fallback path was never exercised after the original cutover, an intervening facade change broke it, and the rollback that was the entire safety argument fails exactly when needed. Correct with scheduled fallback drills including at least one production drill. A fourth is divergence declared acceptable too readily: mismatch classifications lean on "acceptable difference" until the replacement's behavior is materially different from what customers signed up for. Correct with business-side review of the acceptable-difference list per route. A fifth is unbounded mirror cost: mirroring every route at full rate doubles load on shared dependencies and the bill, discovered in the invoice rather than the plan. Correct with ramp-based mirroring and rate caps per route. A sixth is state skew between systems during gradual cutover: data written through the legacy path is invisible to the replacement and vice versa, so a user flipped mid-stream sees stale state. Correct with explicit data-reconciliation for the transition period or session-sticky routing with state synchronization.

## Limitations

The pattern requires an interception point — a route, domain, or request boundary where traffic can be steered — and systems with no such seam (embedded libraries, batch pipelines with fixed callers) cannot use it without building the seam first, which is its own project. Mirroring validates responses, not user experience at scale: it can prove equivalence for observed traffic but cannot exercise load the replacement has never carried, so the first full-traffic moments remain a genuine step into uncertainty. The approach presumes the legacy system keeps running throughout, which caps migration duration by the legacy system's remaining viability — a system weeks from unmaintainability cannot be strangled slowly. Dual-running costs are real and continuous: double infrastructure, double monitoring, reconciliation logic, and the facade itself, all of which exist only to be deleted. Comparability degrades when the replacement is intentionally better: as soon as its behavior deliberately diverges (new pagination, richer errors), diffing stops being a clean oracle and progress has to be managed by judgment instead. Finally, session stickiness and state synchronization during gradual cutover remain genuinely hard for stateful systems, and for those, the pattern's clean percentage ramps collapse into a much more coupled migration.

## Canonical sources

- Fowler — StranglerFigApplication (bliki, 2004): https://martinfowler.com/bliki/StranglerFigApplication.html
- Microsoft Azure Architecture Center — Strangler Fig pattern: https://learn.microsoft.com/en-us/azure/architecture/patterns/strangler-fig
- Microsoft Azure Architecture Center — Gateway Routing pattern (the interception facade the fig grows around): https://learn.microsoft.com/en-us/azure/architecture/patterns/gateway-routing
- Cloudflare Workers — Service bindings (facade-to-backend routing without public hops): https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
