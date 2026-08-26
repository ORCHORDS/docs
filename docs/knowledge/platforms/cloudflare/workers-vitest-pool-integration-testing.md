# workers-vitest-pool-integration-testing

**Issue:** Testing Cloudflare Workers with mocked globals (`fetch`, `caches`, KV stubs) produces tests that pass while the real workerd runtime rejects the code — compatibility flags, binding shape, D1 SQL dialect, and Durable Object semantics all diverge from Node. `@cloudflare/vitest-pool-workers` fixes this by running the tests inside workerd (via Miniflare 3) with your actual wrangler config, so `env` bindings in tests are the real D1/DO/KV/R2 bindings, not approximations. Teams that skip it ship binding regressions and DO alarm bugs that only surface on deploy; teams that adopt it badly (module-scope state, unisolated storage, shared sessions) get flaky tests instead. This article covers setup, the test APIs that matter, and the isolation model.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Setup and configuration

1. **Install the pool and point it at wrangler.** Add `@cloudflare/vitest-pool-workers` as a dev dependency, then in `vitest.config.ts` set `test.pool: "workers"`, `test.wrangler.configPath` to your wrangler JSON/TOML, and import the plugin (`import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config"`). The wrangler config — not the vitest config — remains the single source of truth for bindings.
2. **Override bindings per test run under `miniflare`.** The `test.miniflare` object patches the wrangler-provided bindings: swap in test KV values, point a service binding at the code under test, set D1 database options. Use it for fixtures, not as a second config file that drifts.
3. **Run migrations and D1 setup declaratively.** With `test.miniflare.d1Databases` and the `applyD1Migrations` option, migrations run against the test database before tests — no manual `wrangler d1 migrations apply` step in CI, and schema drift between environments becomes impossible.
4. **Match versions deliberately.** The 0.12.x line supports Vitest 3; 0.13.x supports Vitest 4 (there is an official migration guide). Pin both versions in devDependencies — a floating Vitest major will break the pool on install.
5. **ES modules only.** Service-worker-format Workers are not supported; the pool assumes module syntax with exports. Legacy code must be converted before this testing approach applies.

## The test APIs that matter

1. **`env` from `cloudflare:test`.** Importing `env` inside a test yields the real bindings object (D1, DO namespaces, KV, R2, Queues, AI) as configured. This is the difference between unit tests that mock and integration tests that execute — `env.DB.prepare(...)` runs actual SQLite under workerd.
2. **`SELF` for full-stack round trips.** `SELF` is a fetcher bound to the Worker under test: `const res = await SELF.fetch("https://example/api/x")` exercises the real `fetch` handler, routing, middleware, and error paths — an integration test without deploying anything.
3. **`runDurableObjectAlarm`.** Alarms do not fire on their own schedule in tests; call `runDurableObjectAlarm(namespace, id)` to trigger the alarm handler deterministically and assert its side effects. This is the only sane way to test alarm-driven TTL sweeps and retry logic.
4. **Storage introspection helpers.** Helpers to duplicate/clone Durable Object storage let you snapshot a populated DO, run a mutation, and restore — enabling stateful edge cases (conflict paths, idempotency) without rebuilding fixtures per test.
5. **Setup files for cross-cutting fixtures.** `test.setupFiles` run inside the workerd environment; use them to seed D1 rows, create test objects in a namespace, or register outbound-fetch mocks once per file instead of per test.

## Isolation and flake control

1. **`isolatedStorage` by default.** The pool gives each test file isolated storage semantics — data written by one file does not leak into another; per-test isolation requires `isolatedStorage` (default on) plus discipline: within a file, tests share storage, so either clean up in `beforeEach` or use unique keys per test.
2. **No cross-file persistence.** Storage does not persist between test files even when they share a config; design fixtures accordingly rather than relying on execution order, which Vitest parallelizes anyway.
3. **Control time instead of sleeping.** Use fake timers and DO alarm invocation rather than `setTimeout`/real delays — wall-clock waits are the top source of CI flakes with this pool.
4. **Beware module-scope state.** The module under test is reloaded per test file but shared within a file; module-global caches (config parsed once, memoized clients) must be resettable, or assertions bleed across tests.
5. **Outbound network is opt-in-ish.** Real `fetch` to the internet from tests is possible and usually undesirable; stub outbound services (via service bindings or fetch mocking in setup) so CI does not depend on third-party uptime.

## What to test at each layer

1. **Unit: exported functions.** Anything exported from the Worker (handlers, pure logic, schema helpers) is importable directly in tests — fast, no request overhead, ideal for edge cases and fuzz inputs.
2. **Integration: `SELF` request paths.** Route the important request matrix through `SELF` — auth accepted/rejected, cache headers, error mapping — asserting both status codes and binding side effects (D1 rows written, KV keys set).
3. **Contract: DO and Queue interactions.** Construct DO stubs via `env.MY_DO.idFromName(...)` and drive them directly, including alarm runs; for Queues, assert `sendBatch` payloads and consumer handler behavior with the real binding shape.
4. **Migration tests.** With migrations applied into the test D1, add a test that exercises every repository query post-migration — catches `ALTER TABLE` mistakes that only appear at runtime.
5. **Keep deploy-shape parity.** The vitest config should reference the same wrangler config CI deploys; a separate test-only config is how runtime-only flags (`nodejs_compat`, compatibility dates) silently diverge between test and prod.

## References

1. **Vitest integration.** developers.cloudflare.com/workers/testing/vitest-integration/ — setup, config options, and model.
2. **Write your first test / Test APIs.** developers.cloudflare.com/workers/testing/vitest-integration/write-your-first-test/ and /test-apis/ — `env`, `SELF`, `runDurableObjectAlarm`.
3. **Recipes and migration guides.** developers.cloudflare.com/workers/testing/vitest-integration/recipes/ — D1 and DO testing examples; Miniflare 2 and Vitest 3-to-4 migration guides.
