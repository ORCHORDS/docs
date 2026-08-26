# api-mock-fidelity-schema-locking

**Issue:** Hand-written mocks (MSW handlers, WireMock stubs) pass every test while modeling an API that stopped existing months ago: wrong field names, always-200 responses, missing error envelopes. The suite stays green and production breaks. This article is about mock fidelity — keeping mocks provably consistent with the real API via OpenAPI-locked generation, schema validation of mock responses, and continuous drift detection. It covers hand-written handler drift; recorded-traffic (HAR) fixture governance is a separate article. Based on the MSW "keeping mocks in sync" recipe, MSW Source, openapi-backend, and PactFlow's Drift approach (2025).

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How mocks drift and what it costs

1. **Handlers are typed by nothing.** An MSW handler returning `{ user_name: "Alice" }` when the API moved to `userName` fails no test, because the mock IS the server in the test run. The bug surfaces only in staging — the classic "mocks pass, prod fails" gap.
2. **Copy-paste handler sprawl.** Ten tests each paste the same response object; the API changes one field, someone updates three of the ten handlers, and now the suite tests two different fictional APIs that disagree with each other.
3. **Happy-path-only mocking.** Hand-written mocks almost always return 200 with a full happy object, so client error handling (retry, toast, empty-state) ships with zero test coverage because no mock ever taught it to fail.
4. **Silent time decay.** Mocks written when the endpoint launched keep working after v2 adds required headers, pagination tokens change format, or a rate-limit envelope wraps every response — nothing re-checks mocks against reality unless you build it.
5. **The cost curve is asymmetric.** A drifted mock costs a staging or production incident and a debugging session; the fidelity mechanisms below cost minutes of CI. Teams that skip them are not saving time, they are deferring it with interest.

## Lock mocks to the schema (OpenAPI as source of truth)

1. **Generate handlers from the spec instead of hand-writing them.** MSW's Source package (2025) generates request handlers directly from an OpenAPI document or HAR file, and hey-api/openapi-ts does the same for typed clients — handlers become a build artifact of the contract rather than prose. When the API changes, regenerate; the diff is reviewable in the PR.
2. **Validate mock responses against the schema at test time.** Combining MSW with openapi-backend validates every mocked response against the OpenAPI definition — a handler returning a shape that violates the spec fails the test immediately instead of shipping a lie.
3. **Use schema examples as the default mock body.** `example`/`examples` blocks in the spec give every mock realistic, reviewed seed data for free; custom per-test handlers override only the fields under test.
4. **Type the handlers, not just the client.** If mocks are generated from the same OpenAPI doc as the frontend's typed client, a field rename breaks mock compilation rather than a runtime integration — the type error is the drift alarm.
5. **Forbid hand-editing generated handlers.** Either change the spec (and the real API follows it) or override at the test level; a hand-patched generated file is the worst of both worlds — it looks governed and isn't.

## Detect drift continuously

1. **Run a fidelity test: same request against mock and real API, diff the shapes.** Periodically replay a corpus of requests (from a recording or a canned scenario suite) against both the mock server and a real staging instance and assert structural equality — the direct answer to "do mocks still model the API?"
2. **Check spec ↔ implementation conformance in provider CI.** PactFlow's Drift (2025) runs deterministic conformance checks between the OpenAPI definition and the actual implementation, catching the upstream half of drift: when the provider ships behavior the spec (and therefore your mocks) never described.
3. **Alert on unmodeled endpoints.** If the spec gains an endpoint or a response variant that no mock covers, that is new surface with zero test coverage — generate a handler and at least one test as part of the spec-update PR.
4. **Version mocks with the API version they model.** Tag mock fixtures (`user-api@2026-03-spec`) so a test failure can be traced to a stale contract rather than a code bug; see the HAR governance article for the recorded-traffic version of this rule.
5. **Make regeneration a CI check, not a convention.** A CI step that regenerates handlers from the spec and fails on a diff forces the PR that changes the API to also update every consumer mock — conventions rot, diffs don't.

## Error-path fidelity (the half mocks never model)

1. **Mock the real error envelope, not just status codes.** If the API wraps errors as `{ error: { code, message, retryable } }`, mocks returning bare strings train the client to parse an API that doesn't exist. Copy the envelope from the spec's error responses.
2. **Cover the 4xx/5xx matrix per endpoint.** At minimum: 400 validation (with the real field-error shape), 401/403, 404, 409 conflict, 429 rate limit, and one 5xx. Each maps to a distinct client code path (retry vs re-auth vs surface-to-user) that is otherwise untested.
3. **Simulate realistic latency and failure timing.** A mock answering in 0ms hides every race, timeout, and loading-state bug. MSW/WireMock delay options let one handler test the 3s-slow and 30s-timeout cases explicitly, not accidentally.
4. **Model pagination, empty states, and partial data.** First page / middle page / last page / empty list / single item are five different client behaviors; a mock that always returns a full first page tests one of them.
5. **Keep one small set of real-provider integration tests.** Mocks, however faithful, are still fiction; a thin smoke layer against the true API (or its staging) is the ground truth that tells you when all the above has finally drifted anyway.

## Related

- `mock-server-msw.md` — MSW handler basics
- `wiremock-patterns.md` — WireMock stubbing for JVM/HTTP integration tests
- `playwright-har-replay-fixture-governance.md` — governing recorded-traffic fixtures (the sibling problem)
- `schema-driven-api-fuzzing-schemathesis.md` — fuzzing real APIs against their schema
- `contract-vs-integration-test-boundaries.md` — where mocks fit in the boundary strategy
