# Canary Deployment Automated Rollback SLI Check

A canary is a controlled, small-percentage release whose purpose is to surface a regression
before it reaches most users. The value of a canary is not in *running* it; it is in
*automatically deciding* whether to keep it, advance it, or roll it back. That decision is an
SLI check: the canary is compared to the baseline (the previous version carrying the rest of the
traffic) on a service-level indicator, and the comparison either satisfies a pre-agreed
threshold or triggers a pre-agreed rollback. Without an explicit SLI, the canary becomes a
hope — the human on call watches dashboards for the duration and reasons about whether to
proceed, which is exactly the judgement the canary was supposed to remove.

## Scope

Covers the design of automated rollback for canary deployments based on SLI comparison:
choice of indicator, sampling windows, statistical and absolute thresholds, the wiring that
makes the threshold control the rollout, and the rollback path that the threshold triggers.
Applies to canaries implemented as Workers gradual deployments, Kubernetes-style progressive
delivery with service-mesh traffic splits, and load-balancer-level percentage routing. Does
not cover functional test gates that fire before the canary begins — those are a separate
layer.

## Workflow or implementation guidance

1. **Pick one SLI per canary objective.** A canary that tries to gate on request rate, error
   rate, latency, and saturation simultaneously tends to gate on none of them because no
   threshold fits all four at once. Choose the single indicator that, if it regresses,
   would unambiguously block the release: for a user-facing API this is usually
   *successful request rate* or *99th-percentile latency*; for a worker-driven workflow it
   is often *completion rate*.
2. **Define the comparison explicitly.** The SLI is meaningless without a comparator:
   - baseline: the previous version, on the same SLI, on the same traffic class;
   - delta threshold: an absolute (for example, canary error rate > baseline error rate + 0.5
     percentage points) or relative (for example, canary p99 > baseline p99 * 1.20) bound;
   - sample window: long enough to smooth out noise (commonly five to fifteen minutes for
     steady traffic) and aligned to the canary stage so each stage has its own verdict.
3. **Stage the canary, but make each stage independently verdict-able.** A common pattern is
   1% of traffic for ten minutes, 10% for ten minutes, 50% for ten minutes, then 100%. Each
   stage must end with a binary verdict — proceed, hold, or roll back — produced by the SLI
   check, not by a human watching graphs. Hold is a temporary state in which the canary stays
   at its current percentage while data is collected.
4. **Wire the verdict to the rollout controller.** The canary percentage is advanced or
   reverted by a script that reads the verdict. If the script logs the verdict but a human
   is required to act on it, the canary is not automated and the SLI is decoration. The
   rollout controller must accept the verdict programmatically.
5. **Define the rollback path before the canary begins.** A rollback must be a routing change,
   not a deploy. In Cloudflare Workers, rolling back is moving traffic back to the previous
   version; in a Kubernetes canary it is shifting the service selector back to the baseline
   deployment. Document the exact command, the exact version targets, and the time it takes to
   take effect. A canary whose rollback requires a deploy is unsafe.
6. **Carry the verdict forward as evidence.** Each stage records the SLI values, the threshold,
   the verdict, and the timestamp. After the canary concludes, the record is the artefact that
   justifies the decision and the audit trail for compliance or incident review.
7. **Tune thresholds with incident data, not intuition.** A threshold that never trips is
   probably too loose; a threshold that trips on noise is too tight. After every incident
   that the canary did not catch, adjust the threshold and document the adjustment.

A representative canary configuration for a Workers-based API: stage 1 sends 1% of traffic to
the candidate version for ten minutes, the verdict evaluates `candidate.errorRate <=
baseline.errorRate + 0.5pp` over the ten-minute window, and on pass the script advances to 10%
with the same check. On fail the script reverts traffic to 100% on the previous version in one
step.

## Controls

- Every canary stage has an explicit SLI, comparator, threshold, and sample window. Stages
  without these are not allowed to start.
- The verdict is computed by a script and consumed by the rollout controller. There is no
  human gate in the verdict path.
- The rollback command is rehearsed and time-boxed. A rehearsal that takes longer than the
  canary stage itself is a rollback that fails under pressure.
- The threshold change log records every adjustment and the incident that motivated it.
- The verdict record is retained long enough to be useful for post-incident review.

## Validation evidence

- A deliberate regression is injected on the canary version; the verdict returns fail and the
  controller reverts traffic. The rehearsal proves the wiring.
- A clean release moves through all stages with no threshold trips; the verdict record shows
  steady-state SLI values at each stage.
- A historical review of canaries correlates threshold trips with incidents; thresholds that
  trip on noise are tightened, thresholds that miss incidents are loosened.
- Rollback latency is measured; a rollback that takes longer than the agreed budget is fixed
  before the next canary runs.

## Failure modes and correction

- *Threshold too tight, canaries constantly fail.* Lower the threshold, lengthen the sample
  window, or both. Constant false positives erode trust and eventually someone disables the
  automation.
- *Threshold too loose, regression ships.* Tighten the threshold and shorten the window if the
  canary's purpose is to catch fast regressions. Do not widen the window to fit a single
  noisy stage.
- *Multiple SLIs compared manually.* Pick one SLI per canary objective and let the verdict
  script make the call. Human judgement between two indicators is exactly what the automation
  was supposed to remove.
- *Rollback is a deploy, not a routing change.* Treat as a defect: the canary is unsafe to
  run until rollback is a routing change that takes seconds.
- *Sample window aligned to clock minutes while the SLI depends on traffic bursts.* Align the
  window to rolling buckets of N requests instead, so the verdict is robust to spikes.
- *Verdict computed but not consumed.* The rollout controller must read the verdict; if it
  does not, the canary is decorative. Fix the wiring before the next canary.
- *Threshold tuned against synthetic traffic.* A threshold that holds against load tests but
  trips under real traffic has been tuned on the wrong distribution. Use production-derived
  data and revisit after each incident.

## Limitations

- An SLI-based canary verifies one or two indicators; it does not verify correctness in the
  sense of "did the response match the contract". Functional correctness needs its own
  contract or integration gate, ideally before the canary.
- The verdict assumes baseline and canary share the same traffic class. If the canary is
  routed only to a subset (for example, a single region), the SLI is comparing different
  populations and the verdict can be misleading.
- Statistical comparisons need sufficient sample size. A 1% canary on a low-traffic service
  produces too few samples for the verdict to converge; either raise the percentage or
  lengthen the window deliberately and accept the slower rollout.
- The canary protects only the indicators it monitors. A regression in cost, security, or
  fairness can still ship; those need their own pre-prod gates.
- Automated rollback only works if the system is reversible. A canary that performs
  irreversible side effects (real charges, real emails, real state changes) cannot be
  rolled back by routing alone; it must be guarded by a feature flag or a shadow-write
  pattern.

## Canonical sources

- Google SRE, *Canarying Releases* chapter of the SRE Workbook (SLI design, automated
  rollback, and staged rollout practice): https://sre.google/workbook/canarying-releases/
- Google SRE, *Release Engineering* chapter of the SRE book (canary as part of the release
  pipeline): https://sre.google/sre-book/release-engineering/
- Cloudflare, *Gradual deployments* (canary stages, automated rollback thresholds, and
  rollout wiring for Workers): https://developers.cloudflare.com/workers/configuration/versions-and-deployments/gradual-deployments/
