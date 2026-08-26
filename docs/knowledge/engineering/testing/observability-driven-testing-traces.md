# observability-driven-testing-traces

**Issue:** Traditional integration and E2E tests assert only on the response the caller receives: status 200, the right JSON body, the right rendered page. In a distributed system (an API front end, a Cloudflare Worker, a queue consumer, a database writer) a request can return the correct answer while silently taking a degraded path — a retry storm, a fallback to stale cache, a dropped span of work, a queue message processed twice, a downstream call skipped by a misconfigured circuit breaker. Trace-based testing, the core practice of Observability-Driven Development (ODD), closes this gap by asserting against the OpenTelemetry trace the request generates: which services were called, in what order, with what attributes, durations, and error statuses. The engineering problem is instrumenting every component with OpenTelemetry, writing assertions against spans rather than responses, and running those assertions in CI and against production traffic without drowning in flaky trace-fetch races.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What trace assertions add over response assertions

1. **Path verification, not just outcome.** A trace assertion can require that a checkout request contains an auth span, a payment span, and an inventory-decrement span in causal order. Response-level tests pass when a fallback silently skips the inventory update; the trace test fails immediately because the expected span is absent.
2. **Cross-service causality.** Because OTel propagates trace context across HTTP, queue headers, and cron triggers, one trace id stitched by the test ties the Worker, the queue consumer, and the database write together. This verifies wiring that no single-service test can see, replacing fragile multi-service stub environments for a class of integration bugs.
3. **Inline metadata assertions.** Span attributes (user tier, cache hit/miss, retry count, feature flag values) become assertable contract. Asserting cache.miss is false on the second identical request catches inverse cache bugs that don't change the response at all.
4. **Latency and error-status gates.** Trace tests naturally assert p-latency budgets per span and that no span carries an error status, giving per-request performance regression detection far cheaper than full load-testing campaigns.

## Tooling landscape

1. **Tracetest.** The CNCF project (now Kubeshop/Tracetest) is the reference open-source tool: it triggers a request, polls the OTel collector or vendor backend for the resulting trace, and evaluates YAML assertions against selected spans. Its spec files version-control alongside code and run in CI.
2. **Vendor-integrated equivalents.** Datadog Test Visibility and Elastic's trace-based testing with Tracetest integration let assertions run against production telemetry backends, so the same assertion suite can run pre-merge against a staging environment and continuously against production canaries.
3. **OTel Collector as the test chokepoint.** Even without a trace-testing product, point an OTel Collector at the test environment, export to a file or in-memory backend, and assert with plain test code after awaiting the trace. This keeps the pattern in-repo and free of vendor lock-in.
4. **Trace-trigger separation.** Keep the trigger (HTTP call, event publish, cron fire) decoupled from the assertion step so the same trace spec can be driven by CI, by a scheduled canary, or by replaying production traffic through a shadow environment.

## Avoiding flakiness in trace-based tests

1. **Await the trace, never poll blindly.** Traces arrive asynchronously (batch export defaults to seconds). Tests must wait for trace completion with a bounded timeout — for example, poll until the root span shows the expected number of children or until a terminal span appears — rather than asserting immediately after the response returns.
2. **Assert on ordered relations, not timestamps.** Wall-clock spans from different hosts skew. Assert parent-child relationships and sequence within the trace, not absolute durations, unless the collector applies clock-sync correction.
3. **Sampling strategy for tests.** Test environments must run head sampling at 100 percent; production canaries driving the same assertions need a deterministic sampler keyed on a test-injected attribute (for example, a traffic.test flag) so assertions never depend on probabilistic sampling luck.
4. **Stable span names.** Instrument with low-cardinality, stable span names (checkout.payment, not checkout.payment.4242) and treat span-name changes like API contract changes: update assertions in the same PR.

## Adoption strategy

1. **Start with the worst incident class.** Pick the failure mode that produced past production incidents (duplicate queue processing, fallback masking, swallowed retries) and write trace assertions that would have caught it. Demonstrating that gap justifies the instrumentation work.
2. **Instrument incrementally with standard semantics.** Follow OTel semantic conventions for HTTP, messaging, and database spans so assertions survive library upgrades and tools can auto-detect structure. Custom attributes supplement, not replace, conventions.
3. **Layer with existing test tiers.** The OpenTelemetry demo team's 2023-2025 experience: trace tests complement rather than replace response-level tests. Keep unit tests for logic, E2E for user-visible flows, and add one trace test per critical multi-service flow, not per endpoint.
4. **Promote to continuous verification.** Once a trace assertion is green in CI, mirror it as a scheduled production check (synthetic request plus the same spec) so post-deploy drift — a misrouted canary, a disabled consumer — pages someone instead of waiting for user complaints.
5. **Cost control.** Trace retention and CI telemetry volume cost real money; export only the test-marked traces at full fidelity, sample the rest, and prune attributes with sensitive payloads before they reach the assertion backend.
