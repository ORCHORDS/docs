# Workers Smart Placement Read-Regression Testing

Smart Placement moves a Worker away from the edge and closer to the origin servers or databases it talks to, on the theory that spending a few extra milliseconds on the network hop to the Worker is cheaper than tens of milliseconds of Worker-to-origin latency. The optimization is real, but it is a prediction, not a guarantee: workloads whose heavy dependencies are themselves distributed, or whose users cluster near a colo that placement would abandon, can end up slower. Read-regression testing is the discipline of measuring user-visible latency before and after enabling placement, with enough rigor that the "after" numbers can be trusted.

## Scope

Applies to any Worker where Smart Placement is being enabled, changed (for example switching the placement mode), or where a significant dependency topology change occurs after placement was enabled. Covers latency measurement design, cohort comparison, and the decision to keep or revert placement. Does not cover regional restrictions of data residency, which are a separate mechanism, nor does it cover Durable Objects placement decisions that follow their own rules.

## Workflow or implementation guidance

1. Establish the baseline before touching placement. Capture at least a week of latency telemetry segmented by user geography and by request class, so post-change comparison has variance context rather than a single average.
2. Instrument the Worker to emit timing spans for the full request and for each significant subrequest or database call. Placement changes where subrequest latency accrues, so aggregate-only measurements hide the mechanism.
3. Record the current placement status of the Worker (whether Smart Placement is enabled and, if observable from metrics, where it has been placing execution) so the baseline is attributable.
4. Enable Smart Placement and let the system observe enough traffic to settle on a placement. Treat the first hours after enabling as a warm-up excluded from comparison.
5. Collect a matched window of post-change telemetry, aligned by time-of-day and day-of-week to the baseline window to avoid weekday/weekend bias.
6. Compare distributions, not means: p50, p75, p90, p95 per region and per request class. A placement win at p50 can coexist with a regression at p95 for a subset of users.
7. Attribute the delta. If total latency improved but subrequest latency did not, the improvement may be noise or an unrelated change; if subrequest latency dropped while user-to-Worker hop grew more than the savings, placement chose the wrong location.
8. Decide: keep, revert, or adjust the dependency layout (for example moving a database nearer a consistent region) and re-test. Document whichever decision is made with the measured numbers attached.

## Controls

- Pre-change baseline capture is mandatory; enabling placement without a recorded baseline is a blocked change.
- Regional segmentation control: latency comparisons must be broken out by user geography, since placement trades one region's latency against another's.
- Percentile floor: decisions cite p90 or p95 per region, not global averages alone.
- Attribution requirement: an accepted regression must be explained (which hop changed, in which direction) before sign-off, preventing silent acceptance of a slower configuration.
- Reversion trigger: a defined regression threshold at any monitored percentile for any major region triggers placement review or revert.
- Dependency inventory: the change ticket lists the origins, databases, and services the Worker calls, because placement quality is a property of that inventory.

## Validation evidence

- Baseline and post-change latency tables per region and request class, with percentiles and sample counts.
- Subrequest timing breakdown showing origin-call latency before and after, demonstrating where the improvement or regression occurred.
- The Worker's placement configuration as deployed (Wrangler configuration snippet or dashboard record).
- Settling note stating the warm-up period excluded from comparison and the collection windows used.
- Decision record: keep/revert with the threshold evaluation and the attribution narrative.
- Where available, dashboard metrics or Workers analytics extracts covering the same windows, cross-checking the application-level numbers.

## Failure modes and correction

- Placement enabled on a Worker with no significant origin traffic: overhead of placement analysis without benefit. Correct by disabling placement for edge-pure Workers.
- Users clustered near one colo while the origin sits elsewhere: some users improve, others regress. Correct by evaluating whether the dominant user region justifies pinning behavior instead of automatic placement, or by relocating the dependency.
- Distributed dependencies (many regional APIs) defeat placement: the chooser cannot satisfy all of them. Correct by splitting the Worker so each part sits near its dominant dependency, or accept edge placement.
- Baseline contaminated by another simultaneous change (code deploy, cache change): re-baseline after isolating variables before crediting or blaming placement.
- Warm-up window treated as evidence: placement decisions made on the first hours of data are unreliable; extend the collection window and re-evaluate.
- Metrics conflation between the Worker's execution location and user-visible TTFB when caching layers sit in front: measure the Worker path separately from cached responses.

## Limitations

- Placement decisions are made by Cloudflare's model and are not manually overridable to a specific location in the general case.
- Application-level timing cannot fully separate placement effects from network weather; large sample windows are the only mitigation.
- Very low-traffic Workers may never accumulate enough samples for a statistically confident regional comparison.
- Subrequest timing visibility depends on instrumentation quality; uninstrumented calls are invisible to attribution.
- Third-party origins may shift their own performance between windows, adding uncontrolled variance.

## Canonical sources

- Cloudflare Workers docs, "Placement": https://developers.cloudflare.com/workers/configuration/placement/
- Cloudflare Workers docs, "Limits" (context for measurement constraints on Workers): https://developers.cloudflare.com/workers/platform/limits/
