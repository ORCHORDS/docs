# Cloudflare Workers Subrequest Orchestration Governance

## Purpose

Govern the orchestration of subrequests in Cloudflare Workers so that outbound calls from worker code are deliberate, bounded, and observable: connection reuse, limits, and fan-out behavior are designed rather than discovered when a limit is exceeded in production.

## Scope

Applies to every Worker that issues subrequests (fetch to origin or third-party APIs, cache operations that trigger subrequests, and Workers-to-Workers service bindings usage patterns). Covers subrequest budgeting, egress control, timeout and retry design, and observability. Does not cover routing rules or deployment pipelines.

## Workflow

1. Inventory each Worker's outbound dependencies: destination, purpose, expected call volume per invocation, and whether the call is on the critical path.
2. Budget subrequests per invocation against plan limits: free and paid plans differ; the budget is designed against the binding plan and revisited when the plan changes.
3. Batch and deduplicate where the destination API supports it; N sequential calls for N items is a design smell when a batch endpoint exists.
4. Set explicit timeouts on every outbound fetch and treat silent hangs as failures; a subrequest without a timeout is unbounded latency on the critical path.
5. Apply retry policy deliberately: bounded retries with backoff and jitter, idempotency-gated; retries that multiply on already-failing dependencies amplify outages.
6. Control fan-out: concurrent subrequests are capped per invocation; unbounded parallel fan-out consumes the budget early and starves later logic.
7. Instrument subrequest outcomes (count, duration, status) per destination in structured logs so dependency regressions are visible in aggregate.

## Controls and evidence

- Dependency inventory per Worker with critical-path classification.
- Subrequest budget calculation per Worker against its plan.
- Timeout, retry, and concurrency configuration in code review records.
- Structured subrequest outcome logs per destination.

## Validation

- Confirm each Worker's measured subrequest count per invocation stays within its designed budget under production traffic.
- Confirm every outbound fetch in a sampled Worker has an explicit timeout.
- Confirm retry configuration is bounded and idempotency-gated in the same sample.

## Failure correction

- **Subrequest limit exceeded in production** → reduce calls (batch, cache, deduplicate) before raising the plan; record the design fix.
- **Dependency hang degrading latency** → verify the timeout fired, tune the timeout to the dependency's real profile, and add circuit breaking if it recurs.
- **Retry storm observed** → add backoff and jitter, gate on idempotency, and add a concurrency cap.

## Limitations

- Plan limits change; budgets designed against today's limits need review when plans change.
- Cache and internal APIs can consume subrequest budget in non-obvious ways; measure, do not assume.
- Service bindings behave differently from fetch subrequests; budget them separately.

## Scope note

This article is part of the platforms leaf. Cross-reference: `cloudflare/README.md` (provider index), `CLOUDFLARE_TAIL_WORKERS_OBSERVABILITY.md`, and `monitoring/README.md` (operations leaf).

## Canonical sources

- Cloudflare Docs — Workers subrequests: https://developers.cloudflare.com/workers/platform/limits/#subrequests
- Cloudflare Docs — Workers fetch API: https://developers.cloudflare.com/workers/runtime-apis/fetch/
- Cloudflare Docs — Service bindings: https://developers.cloudflare.com/workers/runtime-apis/service-bindings/
- MDN — Fetch API: https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API
- IETF RFC 9110 — HTTP Semantics (timeouts, idempotent methods): https://datatracker.ietf.org/doc/html/rfc9110
