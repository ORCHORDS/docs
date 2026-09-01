# Blue Green Deployment Test Strategy Mirror Traffic

Blue-green deploys make release safer by exposing two identical environments and shifting traffic
between them rather than deploying in place. The shift is where confidence is won or lost: a
blue environment that passed every functional test can still fail the moment production traffic
hits it, because production traffic carries distribution, header combinations, payloads, and
auth states no test plan enumerated. Mirror traffic — sending a copy of live requests to the
candidate environment and comparing its responses against the live one without affecting users —
collapses this gap. The blue-green test strategy therefore has two layers: the deterministic
gates (contract, integration, smoke) before the cutover, and the replay-and-compare gate during
the cutover, with the comparison itself designed to be safe to act on.

## Scope

Covers the testing strategy around blue-green deploys for HTTP services and Workers-style
request handlers, including pre-shift deterministic checks, the use of traffic mirroring to
surface drift between blue and green, the comparison rules that decide when to abandon the
shift, and the rollback paths that mirror traffic reveals. Applies to platforms that support
gradual deployments and request mirroring — Cloudflare Workers with gradual deployments and
traffic mirroring, Kubernetes with service-mesh mirroring, and equivalent load-balancer
features. Does not cover schema migrations, which require their own dual-write strategy.

## Workflow or implementation guidance

1. **Treat the green environment as immutable between verification and shift.** Once verification
   passes, no further configuration or code change is permitted against green until it has been
   rolled back or promoted. Mirroring compares responses; a moving target invalidates every
   result.
2. **Run the deterministic suite first.** Before any traffic is mirrored, the green environment
   must clear the gates that the platform would not have allowed past a normal deploy:
   contract tests against the live consumers' contracts, integration tests against live
   dependencies, and a synthetic smoke set that exercises health, auth, and at least one
   request path per endpoint. These tests fail fast and cheaply; if they cannot pass, mirroring
   is a waste.
3. **Mirror, do not route.** Mirror means the platform sends a copy of each production request
   to green without returning the response to the user. Cloudflare Workers traffic mirroring
   supports this pattern by replaying requests at configurable percentages while blue continues
   to serve users. The replay rate is dialed up in stages — for example 1%, 10%, 50% — with the
   comparison reviewed at each stage.
4. **Define the comparison policy explicitly.** A naive byte-equality check on responses is
   brittle and noisy; an unstated rule is even worse. Document and version:
   - status code must equal the live response code;
   - content type must equal the live response type;
   - for any header the test policy names (cache-control, content-type, strict-transport-security,
     set-cookie keys), value must equal the live response;
   - body diff tolerance: either strict equality, or a whitelist of fields where drift is
     allowed (request ids, timestamps, ordering of unrelated records);
   - duration: green must not exceed blue by more than a configured percentage (commonly 10–25%
     at the 99th percentile), otherwise green is removed from the candidate set.
5. **Sample, do not capture everything.** Mirror a fixed percentage of live traffic and a fixed
   number of requests per minute so the comparison log stays bounded. The aim is a defensible
   sample, not full fidelity; the production response is the ground truth.
6. **Watch the canary metrics as a separate signal.** Mirror comparisons do not replace
   golden-signal metrics (latency, error rate, saturation) on the candidate environment. A
   response that is byte-equal but takes ten times as long is still a regression.
7. **Pre-define the abort threshold and have it wired to the shift control.** If mirrored
   divergence exceeds threshold or error rate on green exceeds blue by the agreed margin,
   the cutover does not proceed. There must be no human judgement in the loop during the
   shift: the script either advances the percentage or rolls back.
8. **After a successful cutover, keep blue warm for the agreed rollback window.** The whole
   point of blue-green is that rollback is a routing change, not a deploy. Mirror traffic
   stays on blue for at least the rollback window so any post-cutover regression is detectable
   by replay.

A representative Cloudflare Workers gradual-deployment configuration: 1% of traffic mirrors to
the candidate version for ten minutes; if response divergence and 99th-percentile latency on the
candidate stay within bounds, traffic shifts to 10% with the same wait, then 50%, then 100%.
A regression at any stage is treated as a rollback signal — routing reverts to blue and the
candidate version is removed from circulation.

## Controls

- Deterministic suites (contract, integration, smoke) gate the start of mirroring, with results
  attached to the version promotion request.
- The mirroring percentage is incremented only by an automated stage that reads the abort
  threshold; manual overrides require approval and are recorded.
- The comparison policy is committed, versioned, and reviewed by the team owning the service
  before each release that changes it.
- The abort threshold is wired to the cutover script so a regression cannot be reasoned through
  while traffic is being shifted.
- Mirror traffic logs are retained for a configured period and reviewed for the divergence
  patterns they show, not only for the pass/fail of the cutover.
- The rollback procedure is rehearsed on a non-production day, not only when something breaks.

## Validation evidence

- A deliberate divergence is injected in green and the cutover is observed to abort rather than
  complete. This is the rehearsal that proves the abort threshold is wired.
- A normal release is mirrored through 1/10/50/100 stages with no divergence alarms, and the
  rollback window's blue-warm period shows no post-cutover regression.
- Comparison log shows responses diffed on the documented fields only, and the number of
  diffs at each stage is reviewed against the expected noise (timestamp, request id) before
  promotion.
- Latency metrics for green remain within the configured percentage of blue at the 99th
  percentile at every stage of the cutover.

## Failure modes and correction

- *Strict byte-equality rejects every request because of timestamps.* Replace with a structured
  comparator that ignores agreed drift fields; do not lower the bar by disabling the comparator.
- *Green passes mirroring but is slower than blue.* The deterministic suite did not load green
  with realistic concurrency. Add latency budgets to the suite and re-mirror.
- *Cutover proceeds despite mirror divergence because the comparison is not wired to the gate.*
  Fix the wiring: the stage advance script must read the comparison output as a precondition.
- *Mirror traffic consumes the production quota on a downstream service.* Apply a hard cap on
  mirror percentage; do not increase the cap without coordination with the owner of the
  downstream service.
- *Comparison logs grow unbounded and exhaust storage.* Sample to a fixed rate and rotate; keep
  only enough to reconstruct what divergence looked like during the cutover.
- *Rollback rehearsed only on paper.* The first time rollback runs is when production is broken.
  Schedule a quarterly rehearsal against staging.

## Limitations

- Mirror traffic exercises the same code path as live traffic, but it does not exercise side
  effects. A mirrored write to a downstream system duplicates the write; ensure mirrored paths
  are read-only or guarded by an environment marker so the comparison does not double-write.
- Mirrored comparison is structural, not behavioural. A green response that is correct on every
  field can still encode a semantic regression that only a downstream consumer notices.
- The mirror infrastructure must be production-reliable; if mirroring itself fails the
  cutover script must treat that as a non-green verdict rather than fall through.
- Mirroring does not catch regressions in user flows that require session state the mirroring
  layer does not replay; pair with synthetic journey tests that walk the green environment with
  authentic state.
- The strategy presumes deterministic environment parity. Configuration drift between blue and
  green — DNS, feature flags, secrets — will manifest as mirroring noise that masks real
  regressions.

## Canonical sources

- Cloudflare, *Gradual deployments* (traffic mirroring, staged rollout, automatic rollback
  thresholds for Workers): https://developers.cloudflare.com/workers/configuration/versions-and-deployments/gradual-deployments/
- Cloudflare, *Versions and deployments overview* (configuration of immutable candidate
  versions and rollback semantics): https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
- Google SRE, *Release Engineering* chapter of the SRE book (blue-green, canary, and rollback
  practice at scale): https://sre.google/sre-book/release-engineering/
