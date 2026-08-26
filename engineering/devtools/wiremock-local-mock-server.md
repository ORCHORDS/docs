# wiremock-local-mock-server

**Issue:** Testing code that talks to external HTTP APIs — this repo's connectors package calls multiple model providers, and the example project worker calls third-party services — has three bad options: hit real APIs in tests (slow, flaky, costs money, leaks keys), hand-roll a stub server (drifts from the real contract, no edge cases), or skip integration coverage entirely. A proper mock server gives you deterministic responses, latency and fault injection, stateful multi-step conversations, and request assertions, all recorded for test assertions. The 2025-2026 landscape splits between WireMock (rich dynamic behavior, templating, scenarios) and Stoplight Prism (OpenAPI-spec-driven, near-zero config when a spec exists). This article covers building a local mock-server layer for API-adjacent code, WireMock 3.x specifics included, and how it complements the proxy-debugging tools already in this knowledge base.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## WireMock versus Prism, and when to use each

1. **WireMock for dynamic behavior.** Hand-rolled HTTP server (JVM, also distributed as a static binary and Docker image) with request matching on URL/method/headers/body (JSONPath, XPath, regex), response templating via Handlebars, fault injection (delays, empty responses, bad payloads), and stateful scenarios. Use it when tests must exercise retries, backoff, rate-limit handling, and malformed-response paths — exactly the behaviors a connectors library needs proven.
2. **Prism when an OpenAPI spec exists.** Stoplight Prism spins a mock directly from the spec file: examples and schema-derived responses for free, plus request validation that flags when your client drifts from the contract. Zero stub definitions to maintain, but limited dynamic logic. Ideal for consumer-contract testing against a published spec; weak for fault choreography.
3. **They compose with the recorded reality.** A pragmatic 2025 stack: capture real traffic with mitmproxy (see this repo's mitmproxy article), replay its exported stubs into WireMock, and hand-edit the interesting cases. Mock fidelity stops being guesswork.
4. **Local-first operation.** `wiremock --port 8080` runs a standalone server from the binary/Docker image (`wiremock/wiremock` image, WireMock 3.x is the current major); point the code under test at `http://localhost:8080` via an env var and the same harness runs in CI with no network.

## Stubbing model essentials

1. **Request matching precedes everything.** A stub pairs a matcher (URL path, query params, headers, body patterns) with a response. Unmatched requests hit WireMock's default 404 plus a diagnostic — always assert on near-misses first; most "mock is broken" bugs are a matcher that does not match (trailing slash, content-type header, body JSON formatted differently).
2. **Priority resolves overlapping stubs.** Stub matching is scored, and explicit `priority` (lower wins) disambiguates: a specific-error stub at priority 1 can shadow a catch-all success stub at 5. This is the standard trick for "first call fails, then succeed" tests.
3. **Verify requests, not just responses.** WireMock records every request; `GET /__admin/requests` and the Java/JS client's `verify` API let tests assert the client sent the right payload, headers, and retry cadence — the assertions that prove connector logic, which response assertions alone cannot.
4. **Serve realistic payloads from files.** `bodyFile` keeps large fixture JSON (sample provider API responses) out of test code and under version control next to the stub definitions.

## Templating and stateful behavior (WireMock 3.x)

1. **Response templating is Handlebars with superpowers.** Templates echo request data (`{{jsonPath request.body '$.model'}}`), generate values, and compute conditional bodies — one stub can answer every model name the router tests throw at it. The official response-templating docs catalog helpers (now including JSONPath and XPath helpers).
2. **3.x made templating opt-in — a real migration trap.** In WireMock 2.x the transformer frequently applied implicitly; in 3.x you must either enable global response templating at startup or attach the transformer per stub. GitHub issue wiremock/wiremock#2816 documents teams whose `{{...}}` literals started passing through literally after upgrading. If templates render raw, this is why.
3. **Scenarios model stateful conversations.** Stubs declare `whenScenarioStateIs`/`willSetStateTo` so the same endpoint returns STARTED, then PENDING, then DONE across successive calls — pagination, auth token flow, and "fail twice then recover" retry tests become declarative. Scenarios and templating combine for state-dependent bodies.
4. **Fault injection is first-class.** `fixedDelayMilliseconds`, `chunkedDribbleDelay`, malformed JSON, connection reset (via the fault API) — the exact inputs needed to prove client timeouts, backoff jitter, and circuit-breaker behavior without a chaos harness. Simulating a 429 with `Retry-After` is a three-line stub.

## Running mocks in this repo's workflows

1. **Stubs as files, not imperative setup.** WireMock's file-based stubs (`mappings/` and `__files/` directories) make the mock server state a reviewable artifact: PRs that change expected provider behavior show up as stub diffs. Start the container mounting the repo's mappings directory and the API surface is versioned with the code.
2. **Docker Compose service for local dev.** Add a wiremock service next to the app in docker-compose (see this repo's docker-compose article); the frontend/router can develop against it fully offline — the offline-resilience requirement from the mobile testing protocol becomes testable at the API layer.
3. **CI usage.** Spin WireMock as a service container or the standalone binary in the test job; because state resets per run, tests stay hermetic. Remember to reset scenarios between tests (`POST /__admin/scenarios/reset`) or state leaks across test orderings — the classic flaky-mock bug.
4. **Alternatives worth knowing.** Prism for spec-mocking as noted; Mockoon for a GUI-driven local mock when pair-debugging with non-engineers; nock (JS) only when the code under test is same-process Node and you accept coupling tests to the HTTP client library.

## Related

1. **Adjacent repo articles.** `mitmproxy-api-traffic-debugging.md` and `charles-proxy-debugging.md` for capturing the real traffic mocks are distilled from; `docker-compose-dev.md` for wiring the mock as a service; `bruno-api-client.md` for exercising the mocked endpoints manually.
2. **Primary sources.** wiremock.org docs (stubbing, response-templating, scenario/state pages), wiremock/wiremock#2816 for the 3.x templating change, and Stoplight's Prism docs for the spec-driven path.
