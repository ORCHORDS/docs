# blue-green-vs-canary-decision-matrix

**Issue:** Teams know how to run a blue-green switch and how to run a canary, but when deploy time comes nobody can say which one this particular change deserves. Picking the wrong strategy either doubles infrastructure cost for a trivial config push, or blast-radiuses a risky rewrite to 100 percent of users at once. The per-strategy mechanics are documented in canary-deployments.md, blue-green-traffic-switch.md, and zero-downtime-deploy-strategies.md; this article is the decision layer that sits above them — a repeatable matrix for choosing a rollout strategy per deploy, not per team.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Decision inputs

1. **Change risk class.** Classify the diff before choosing: pure config, additive backend, schema-touching, or protocol/contract change. Current 2025-2026 guidance (CircleCI, Octopus Deploy, Harness) converges on blue-green for straightforward low-risk updates and canary whenever real-user validation must precede full exposure. If the change cannot be classified confidently, default to the more gradual option — canary — because its failure mode is smaller.
2. **Infrastructure budget.** Blue-green requires roughly 2x capacity for the service during cutover because a full idle stack must stay warm for instant rollback (Unleash and others flag this as the main cost objection). Canary runs on existing infrastructure by shifting percentages of traffic. If the service is memory-heavy or runs on GPU nodes, the doubling cost frequently decides the question on its own.
3. **Rollback speed requirement.** Blue-green rollback is an instant traffic switch back to the untouched previous stack — seconds, regardless of how bad the new version is. Canary rollback means re-shifting traffic to old instances that are progressively shrinking. If the stated tolerance for bad-version exposure is under a minute, blue-green wins; if it is minutes-to-hours with metric gates, canary wins.
4. **Metrics maturity.** Canary is only safe if you can statistically detect a bad cohort: per-version error rate, latency percentiles, and a comparison baseline must exist before the deploy starts. Teams without per-version telemetry should not canary — they get blue-green's binary outcome with none of the early warning. Progressive delivery tooling (Flagger, Argo Rollouts) automates the analysis but does not create the metrics for you.
5. **Traffic shape.** Blue-green switches everyone simultaneously, so a bad version hits all user segments at once even if only for seconds. Canary lets you shape the cohort — internal users first, then a single region or a flagged percentage. For business-hours-sensitive workloads (payments, trading), cohort control usually outweighs rollback-speed benefits.

## The decision matrix

1. **Low-risk change, cheap infrastructure: blue-green.** Routine releases where the diff is small and capacity is modest. You pay the doubling cost for a short window and get instant cutover plus instant rollback. This is the classic monolith / small-service case practitioners describe for blue-green.
2. **Low-risk change, expensive infrastructure: rolling update.** When doubling capacity hurts but risk is low, a plain rolling update (the Kubernetes default) is legitimate and avoids strategy theater. Do not use a heavyweight strategy as a ritual; match rigor to risk.
3. **High-risk change, metrics available: canary.** Rewrites, new dependency versions, anything touching hot paths. Start at 1-5 percent, gate each step on error-rate and latency deltas, and let automated analysis promote or abort. The blast radius of a bad deploy becomes the canary cohort instead of the whole user base.
4. **High-risk change, no per-version metrics: blue-green first, fix telemetry after.** Without cohort analytics canary gives false confidence. Take the binary blue-green cutover behind a health-check gate, and file the missing metrics work as a deploy-blocking debt item for next time.
5. **Contract or schema change: neither, until made compatible.** If old and new versions cannot coexist (breaking API contract, non-forward-compatible schema), both strategies are unsafe — blue-green flips atomically but any client cache or in-flight request still straddles versions. Expand-contract the change first (see database-migration-deploy-strategy.md and event-schema-compat-deploys.md), then apply the matrix above to the now-compatible halves.
6. **Both is allowed.** The strategies compose: blue-green each environment for fast rollback, then canary the traffic switch 5-25-50-100 instead of flipping it. This is the standard pattern for high-traffic services where even a seconds-long bad exposure is costly.

## Common wrong choices

1. **Canary as a substitute for testing.** Shipping untested code at 1 percent is not progressive delivery, it is slow-motion production testing. The matrix assumes the change passes CI and pre-deploy verification; the strategy only decides exposure, not correctness.
2. **Blue-green with shared state.** Blue-green assumes the two stacks are independent. If both write to the same rows with different semantics, or share a mutable cache keyed by version-less logic, the idle stack is not really idle-risk-free and the instant rollback is an illusion. Audit shared-state assumptions before choosing blue-green.
3. **Ignoring session drain in the choice.** The matrix outcome must include how in-flight work drains: blue-green needs an old-stack drain window after the switch; canary needs shrinking old pods to finish requests. A strategy chosen without its drain plan is half a decision (see graceful-shutdown-patterns.md and database-connection-drain.md).
4. **Sticky strategy identity.** "We are a canary shop" is an anti-pattern. The matrix should be evaluated per deploy, because a config-only push and a protocol rewrite in the same service have wildly different correct answers.

## Recording the decision

1. **Log the matrix outcome with the deploy.** Record risk class, chosen strategy, and the deciding factor in the deployment notification (see deployment-notification-slack.md). This turns strategy selection into reviewable data instead of vibes.
2. **Revisit quarterly.** As metrics maturity and infrastructure costs change, yesterday's correct default drifts. Review the matrix inputs — not just the outcome — when deployment-frequency metrics show strategy mix shifting without risk-mix shifts.
