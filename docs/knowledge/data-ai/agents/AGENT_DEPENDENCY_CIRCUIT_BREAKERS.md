# Circuit Breakers for Agent Dependencies

## Scope

Agents call models, search services, databases, protocol servers, and business APIs. Repeated calls to an unhealthy dependency waste budgets, amplify outages, and obscure the original failure. A circuit breaker is a deterministic admission control for calls to one dependency operation. It differs from retries and queue backpressure: retries govern another attempt, while a breaker decides whether an attempt may start based on recent outcomes.

NIST SP 800-53 addresses availability, monitoring, and failure handling. The OpenTelemetry metrics specification supplies stable concepts for counters and histograms. This design uses those objectives without treating a breaker as a security boundary or claiming standards conformance.

## Workflow

1. Define a breaker key from dependency, endpoint or operation, region, and workload class. Avoid one global breaker that lets an unrelated operation disable the entire service.
2. Classify outcomes before counting them. Dependency timeouts, connection failures, overload responses, and selected server errors may count; caller validation errors, authorization denials, and intentional cancellations normally do not.
3. In the closed state, admit calls and update a bounded rolling window. Require a minimum sample count before opening so one failure at low traffic does not trip the circuit.
4. Open when the configured failure-rate or latency threshold is exceeded. Reject new calls immediately with a typed dependency-unavailable result until the cooldown expires.
5. Enter half-open with a small, exclusive probe allowance. Normal traffic must not become an uncontrolled probe storm.
6. Close only after sufficient successful probes. Reopen immediately on a qualifying probe failure, with a bounded cooldown policy.
7. Select a fallback only if its semantics are explicitly compatible: stale read, cached capability metadata, alternate region, or human escalation. Never substitute a side-effecting operation with a merely similar one.
8. Propagate a clear result to the planner so it cannot loop around the breaker through aliases.

## Controls, data, and evidence

Keep breaker policy outside prompts. Version thresholds, windows, minimum samples, cooldowns, probe counts, outcome classifications, and approved fallbacks. Use monotonic time for local state transitions. In distributed deployments, choose deliberately between per-instance breakers, which react quickly but differ, and shared breakers, which coordinate but add a dependency. Apply randomization to recovery probes and cap concurrent half-open calls.

Record state transitions, breaker key, policy revision, aggregate counts, threshold reason, probe outcomes, fallback selected, and duration open. Metrics should include admitted, rejected, failed, and probe calls plus dependency latency. Do not attach high-cardinality run identifiers to every metric. Evidence includes threshold rationale, dependency service objectives, fallback approvals, game-day results, and incident reviews showing whether the breaker reduced amplification.

## Validation tests

Inject a sequence below the minimum sample count and verify the breaker remains closed. Cross the configured failure threshold and verify subsequent calls are rejected without network traffic. Ensure caller-caused 400 responses do not open a dependency-health circuit, while selected overload responses do. Simulate slow successes that breach the latency criterion.

Run many workers at cooldown expiry and confirm only the probe allowance reaches the dependency. Make probes fail, then recover, and verify exact transitions. Test that an opened search breaker does not disable an unrelated write endpoint. Confirm stale-cache fallback respects age and authorization. Restart workers and verify the documented persistence behavior. Exercise configuration changes during open state and ensure the new revision has deterministic migration semantics.

## Failure handling

If breaker state storage fails, use a conservative local breaker rather than treating all dependencies as healthy. If classification is uncertain, preserve the original error and avoid counting it until policy decides; a generic failure bucket can alert operators. When a fallback fails, return the original dependency context plus fallback status without recursive fallback chains.

An accidentally overbroad breaker can cause a self-inflicted outage. Operators need a time-bounded override with authentication, justification, and evidence, but an override must not erase counters. If a dependency is corrupt rather than unavailable, open immediately through an explicit isolation signal and prohibit cached fallback unless its integrity is independently established.

## Limitations

A breaker does not repair dependencies, guarantee fair capacity, or replace deadlines, retries, bulkheads, and rate limits. Historical windows lag abrupt changes. Per-instance state may allow excess probes, while shared state can itself fail. A successful probe may not represent production payloads. Breakers based only on transport success cannot detect semantically wrong responses; separate validation must classify those outcomes.

## Canonical sources

- **NIST, SP 800-53 Revision 5:** https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- **OpenTelemetry, Metrics Data Model:** https://opentelemetry.io/docs/specs/otel/metrics/data-model/
- **IETF, HTTP Semantics (RFC 9110):** https://www.rfc-editor.org/rfc/rfc9110.html
