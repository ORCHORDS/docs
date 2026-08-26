# chaos-engineering-verification

**Issue:** The example project platform has retry policies, circuit breakers, timeouts, and multi-AZ deployment on paper, but none of it has ever been verified against a real failure. The first time an AZ degraded, the circuit breaker that was supposed to shed load instead amplified retries and turned a 2-minute blip into a 40-minute outage. Chaos engineering — running controlled failure experiments against production-like systems to verify resilience hypotheses — is the discipline that closes the gap between "we configured a timeout" and "we observed the timeout work." The 2025 practice shift is decisive: teams run chaos as automated verification embedded in CI/CD, focused on validating steady state, not on breaking things for spectacle.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The steady-state hypothesis, written before the experiment

1. **Define steady state as a measurable metric, not a feeling.** "Checkout works" is not a hypothesis; "checkout p99 latency stays under 800ms and success rate stays above 99.5% while measured by RUM" is. The ACM 2025 literature review identifies defining steady-state behavior as one of the three essential activities of chaos engineering — an experiment without a quantified baseline cannot fail, and therefore cannot teach anything.
2. **State the hypothesis explicitly: injecting X will keep steady state within Y.** Example: "Killing one replica of the search service will not move checkout error rate above baseline noise, because the client retries once with jitter." The because-clause names the mechanism under test — if the mechanism is imaginary, that is exactly what the experiment should expose.
3. **Measure steady state from the outside in.** Baseline and verification must use user-visible signals (synthetic probes, RUM, SLI metrics), not internal health checks — a service can report healthy while failing users, which is the entire class of bug chaos exists to find.
4. **Abort conditions are part of the experiment design.** Write down, before starting: what metric excursion halts the experiment automatically (e.g. SLI breaches 3x baseline for 2 minutes), who can abort, and how the fault is switched off even if the control plane is the thing being attacked. An experiment without a kill switch is an outage with paperwork.

## Experiment design: small, specific, escalating

1. **Blast radius first, magnitude second.** Start with 1% of traffic or a single canary pod in one region; the failure mode you are verifying does not require burning the whole fleet. Expand radius and duration only after a hypothesis holds at small scale.
2. **Target the mechanisms you actually depend on.** Priorities: dependency timeout propagation (slow, not down — a 30s hang is worse than a fast 503, see `third-party-api-monitoring.md`), retry storms under partial failure, connection-pool exhaustion, queue consumer death, and failover of the primary datastore. Each maps to a named resilience feature someone claimed in a design doc.
3. **Schedule game days, then automate the winners.** Quarterly game days (a scheduled, staffed experiment window) build organizational muscle and generate findings. Any experiment that validates a critical mechanism then gets encoded as an automated scenario running in staging on every release — the 2025 trend of chaos-in-CI/CD means regression-caused resilience loss is caught at the PR, not at the outage.
4. **Pre-mortem the second-order effects.** Before injecting, list what else shares the blast radius: shared connection pools, rate-limited downstream APIs, cache stampede potential on recovery, and on-call noise (experiments must be labeled in the observability stack so dashboards and alerts annotate "chaos: zone-loss-drill").

## Observability requirements: the experiment is a measurement exercise

1. **Instrument the hypothesis metric before the first injection.** If success rate is the steady-state signal, it must be measurable at the experiment's granularity — a 5-minute-windowed SLI cannot verify a 90-second experiment. Use higher-resolution recording during the window.
2. **Label experimental traffic and spans.** Inject a `chaos.experiment` attribute (baggage or resource attribute) so traces, metrics, and logs from the experiment can be sliced out afterward. Reconstructing "which errors were drill versus real" without labels is manual and wrong.
3. **Watch the recovery, not just the failure.** Half of resilience is what happens after the fault clears: do retries stop, do pools drain, do caches repopulate without stampede, do dropped messages replay? Record steady-state confirmation for a full recovery window after fault removal before declaring the experiment ended.
4. **Capture the verdict as data.** Each run stores: hypothesis, injection parameters, timeline of fault on/off, steady-state metric series, abort conditions evaluated, pass/fail, and links to traces. Failures here are findings to fix, not experiments to rerun quietly until green.

## Governance and safety rails

1. **Run in production only after staging proves the harness.** The harness itself (fault injector, metric watcher, auto-abort) must be tested — a buggy injector that cannot stop injecting is the classic way chaos causes the outage it was meant to prevent. First production experiments run during staffed hours, never during peak, never during an active incident or freeze.
2. **One experiment at a time, one variable at a time.** Concurrent experiments interact (two "small" pod kills compound into a capacity event). Serialize via a shared schedule or a lock in the experiment tooling.
3. **Feed findings into the normal reliability backlog with owners.** A chaos finding without a tracked fix is reconnaissance reported to nobody. Link each failure to an issue, and re-run the scenario as the fix's acceptance test — this closes the loop and makes the next game day measurably boring.
4. **Keep the audit trail.** Who authorized the run, what changed, who was watching, and the abort transcript — required both for internal trust and because regulators and enterprise customers increasingly ask for evidence of resilience testing, not just architecture diagrams.
