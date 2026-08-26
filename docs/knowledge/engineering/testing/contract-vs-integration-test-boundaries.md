# contract-vs-integration-test-boundaries

**Issue:** Teams argue in every review about whether a change needs a contract test, an integration test, or both, and the suite ends up with a slow full-matrix integration sprawl that duplicates what contracts already prove. This article gives the decision boundary: what each layer can and cannot verify, when one replaces the other, and where integration tests remain irreplaceable. Grounded in PactFlow's comparison of the two techniques, Tweag's January 2025 write-up on shifting left with contracts, current bi-directional contract practice, and a 2026 upstream external-auth callback reconciliation.

**Date:** 2026-08-20
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What each layer actually verifies

1. **A contract test verifies the message, not the collaboration.** It proves the request a consumer sends and the response a provider returns are shape-compatible (fields, types, status codes) without ever deploying both services together. PactFlow describes it as borrowing from unit testing (isolated, fast) to get integration-like confidence about the boundary.
2. **An integration test verifies runtime composition.** Real processes, real middleware, real database driver, real serialization — it catches what a contract structurally cannot: latency timeouts, connection-pool exhaustion, transaction behavior, infrastructure misconfiguration.
3. **Contracts scale linearly with consumer×provider pairs; integration suites scale combinatorially.** Ten consumers against ten providers needs 100 contract verifications (cheap, automated per pair) but only a handful of deployed compositions. A full deployed matrix is 100 environments — nobody has that, which is exactly why the matrix gets tested badly or not at all.
4. **Neither layer verifies business logic end-to-end.** Unit tests verify logic, contracts verify the boundary, a thin E2E set verifies the user journey. The Baserock model teams converged on in 2025 is: unit → contract → small targeted integration/E2E, not contract OR integration.
5. **A passing contract does not mean the integrated system works.** A provider can verify every pact and still fail in production because of an infrastructure behavior no contract encodes — Tweag's 2025 post is explicit that contract testing removes many integration tests, not the need for them.

## Decision rules for choosing

1. **Default to contract tests for every consumer-provider API pair.** They give deterministic, fast, deploy-independent verification of the boundary and run in each team's own pipeline. This is the 2025 consensus across PactFlow, Tweag, and Specmatic users.
2. **Write integration tests for the critical business flows, not the matrix.** One or two deep verticals per service (e.g. "payment succeeds", "order ships") through real dependencies; skip the long tail of combinations the contracts already cover.
3. **When two services are owned by the same team and deployed atomically, an integration test may be enough — contracts add little.** Contracts pay off at organizational boundaries where the provider team cannot run the consumer's tests and needs a machine-checkable promise instead.
4. **When you cannot deploy the dependency at all (third-party SaaS, another org's service), contract tests are the only honest option** — you verify your client against the documented/recorded contract because you will never get a joint environment.
5. **Consider bi-directional contracts when cross-team CDC coordination stalls.** PactFlow's bi-directional mode reconciles a consumer's OpenAPI-validated recorded traffic with the provider's published spec, trading some precision (no provider-states replay) for far less process overhead — a pragmatic 2025-2026 pattern for large orgs adopting late.

## Where integration tests remain irreplaceable

1. **Middleware and framework behavior:** routing, auth filters, content negotiation, serialization quirks, error-handling middleware. A contract asserts the wire shape; only running the stack proves the framework produces that shape from the handler you wrote.
2. **Database and migration behavior:** query correctness, transaction isolation, migration ordering, constraint enforcement. Contracts sit above the persistence layer entirely.
3. **Timing and resource behavior:** retries against a slow dependency, timeout budgets, backpressure, connection limits. These properties are invisible to contract matchers.
4. **Infrastructure-as-code verification:** env vars, secrets wiring, network policies, DNS. If the bug class is "the deployed thing is wired wrong," only a deployed test sees it.
5. **Event-driven and async interactions beyond simple request/response.** Message payloads can be contract-tested, but consumer group behavior, redelivery, ordering, and dead-letter handling need a running broker (see `event-driven-testing.md`).

## Fixed upstream callback clients: test what they can actually send

A special integration boundary exists when the "consumer" is an upstream product that owns the HTTP client. Examples include external-auth callbacks, webhook deliveries, storage notifications, identity-provider backchannels, and media-server authorization hooks. Your provider can accept any header you want, but that does not matter if the real upstream client has no documented way to send it.

1. **Treat the upstream producer's documented request as the contract.** Record method, body shape, headers, success status semantics, retries, TLS options, and every configurable authentication field. Do not add an independent required header merely because a hand-written client can provide one.
2. **Never prove compatibility with a curl command the real producer cannot reproduce.** A manual request that adds `Authorization`, custom HMAC headers, query parameters, or a different body can make an impossible integration look green. The acceptance test must originate from the actual upstream software or an exact contract fixture generated from its documented/request-capture shape.
3. **Separate payload authentication from service-to-service authentication.** A callback body may contain end-user credentials or an action token while the receiving service also wants to authenticate the machine making the callback. If the upstream client cannot carry that second credential, preserve the trust boundary with an adapter/sidecar, mTLS or network boundary, or another upstream-supported mechanism; do not silently drop the machine-auth requirement.
4. **Do not assume adjacent hook mechanisms have the same capabilities.** A lifecycle command or script can often set arbitrary headers because your code owns the HTTP request. A product's built-in external-auth HTTP client can have a fixed request contract. Verify them separately.
5. **Prefer a local adapter when translation is the only missing capability.** Bind it to loopback or another tightly scoped local interface, accept only the upstream's exact request shape, forward to the protected service while adding the host/service credential, bound timeouts and body size, and never log raw credentials. This keeps the public provider fail-closed without pretending the upstream supports an option it does not.
6. **Re-check the upstream contract before deployment.** External products evolve. Pin/document the tested version where practical and verify the current vendor docs/config schema before relying on a new field.

### Concrete source-backed example

MediaMTX documents `authMethod: http` / `authHTTPAddress` as a POST to the configured URL with a JSON authentication payload (`user`, `password`, `token`, `ip`, `action`, `path`, `protocol`, `id`, `query`, `userAgent`) and treats a `20x` response as successful authentication. Its current configuration exposes the callback URL, optional TLS-certificate fingerprint, and exclusions, but does not document an arbitrary custom-header setting for that external-auth request. Therefore a receiving endpoint that additionally requires a private custom Bearer header cannot be declared compatible solely because `curl -H 'Authorization: Bearer …'` works.

**Sources:**
- [MediaMTX authentication — External HTTP server](https://github.com/bluenviron/mediamtx/blob/main/docs/2-features/06-authentication.md)
- [MediaMTX current configuration](https://github.com/bluenviron/mediamtx/blob/main/mediamtx.yml)

### Verification checklist for fixed callback producers

- Start the real upstream producer with the intended configuration and capture only non-secret request metadata needed to prove the contract.
- Confirm the provider accepts the exact upstream method/body/header set with no test-only additions.
- Confirm invalid user/action credentials fail.
- Confirm missing machine/service trust fails closed through the chosen adapter/network/mTLS mechanism rather than becoming anonymous access.
- Exercise timeout, non-20x, malformed-body, oversized-body, and restart behavior.
- Assert logs redact callback credentials, service credentials, signed URLs, and tokens.

## Failure modes of picking wrong

1. **Contract theater:** consumer pacts exist but no provider verification runs in the provider's CI, so the broker is a museum of stale promises. If `can-i-deploy` never gates a deployment, you have documentation, not tests.
2. **Integration sprawl:** every service spins up five dependencies in containers "to be safe," CI takes 40 minutes, and teams start skipping the suite. Replace the breadth with contracts; keep depth on critical paths.
3. **Using E2E as a contract substitute:** a brittle UI journey that fails for CSS reasons is a terrible breaking-change detector for an API field rename; a one-second contract test catches it precisely.
4. **All-mocks integration tests:** a test labeled "integration" where every dependency is a stub verifies nothing beyond unit scope — it is an integration test in name only. At least one side must be real.
5. **Duplicated layers with no owner:** the same scenario maintained as a pact, an integration test, and an E2E, each drifting apart. Pick one home per behavior class: boundary → contract, composition → integration, journey → E2E.
6. **Impossible-client green test:** a curl/Postman test supplies authentication metadata the production upstream client cannot emit, so the provider looks healthy while the real integration is guaranteed to fail.

## Related

- `api-mock-fidelity-schema-locking.md` — keep test doubles locked to the real producer/provider contract
- `contract-testing-pact.md` — Pact setup mechanics for consumer and provider
- `consumer-driven-contracts.md` — CDC workflow with broker and `can-i-deploy` gating
- `integration-test-api.md` — supertest-based API integration patterns
- `test-pyramid-strategy.md` — where contracts sit in the overall layering
