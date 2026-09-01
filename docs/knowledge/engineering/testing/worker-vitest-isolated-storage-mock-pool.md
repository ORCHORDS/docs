# Worker Vitest Isolated Storage Mock Pool

Testing a Cloudflare Worker with Vitest means testing code that binds to storage — KV,
D1, R2, Durable Objects — through bindings that do not exist in a plain Node process. Two
strategies dominate. The first uses Miniflare to provide real per-test storage: every test
gets a fresh namespace, a fresh database, a fresh object store. The second uses mocks: a
test double with the same interface as the binding, backed by an in-memory structure the
test controls. A *mock pool* is the second strategy systematised: a shared factory that
hands each test an isolated mock instance, so tests never share state through the mock and
the mock's behaviour is configured per test rather than globally. The isolation property
is the whole point: a mock shared across tests couples them, and coupled tests fail in
orders that nobody can reproduce.

## Scope

Covers the design of an isolated storage mock pool for Vitest tests of Cloudflare Workers,
including the structure of the pool, the per-test lifecycle, the relationship between
mocks and Miniflare-backed bindings, and the pitfalls of shared mock state. Applies to
tests of Worker handlers, Durable Objects, and Queues consumers. Does not cover the
broader Vitest-on-Workers integration configuration, nor the design of the Worker itself.

## Workflow or implementation guidance

1. **Choose mocks for logic, Miniflare for semantics.** A mock is the right choice when
   the test's subject is the Worker's decision logic — "given a KV namespace that
   returns a cached value, the handler returns it without recomputing". Miniflare is the
   right choice when the test's subject is the storage semantics themselves — "the KV
   write with `expirationTtl` is visible for the next read within the TTL". The mock pool
   strategy serves the first case; the second needs the real engine.
2. **Build the pool as a factory, not a singleton.** The pool's interface is
   `createIsolatedEnv()`, which returns a fresh set of mocks (KV, D1, R2, Durable
   Objects, Queues, caches) wired into the shape the Worker's `env` expects. Each test
   calls the factory in its setup; each test receives mocks that no other test has
   touched. A module-level `const kv = new MockKV()` shared by every test is the
   antipattern the pool exists to prevent.
3. **Give each mock the same interface as the real binding.** The mock's methods and
   signatures must match the binding the Worker will receive in production — `get`,
   `put`, `delete`, `list` for KV with the same options and the same return shapes
   (`Promise<string | null>`, cursor-based listing). A mock with a subset of the
   interface passes tests that fail in production the first time the Worker calls a
   method the mock did not implement.
4. **Back the mock with an in-memory structure that models the semantics you rely on.** A
   KV mock backed by a `Map` gives you get/put/delete semantics. Decide deliberately
   which semantics to model — TTL expiry, list cursors, metadata, eventual-consistency
   windows — and model those the Worker's logic depends on. An over-simple mock hides
   real behaviour; an over-elaborate mock reimplements Miniflare and should be replaced
   by it.
5. **Reset state in `beforeEach`, not in module scope.** Vitest's `beforeEach` hook is
   where the factory is called and the mocks are reset. State reset in module scope runs
   once per file, not once per test, and tests within a file share whatever the previous
   test left. Use `vi.resetAllMocks()` with care: it resets call history but not
   necessarily the mock's backing store; the pool's own reset method is explicit about
   both.
6. **Support parallel workers.** Vitest runs test files in separate processes or worker
   threads by default; each file's pool is independent, so file-level parallelism is
   safe. Within a file, tests run serially by default; if `describe.concurrent` is used,
   the pool must hand out distinct instances per concurrent test, not one shared
   instance. Make the pool's contract explicit: one isolated env per test, always.
7. **Record interactions for assertion.** The mock records calls (arguments and results)
   alongside its state. Assertions can then check both outcomes and interactions:
   `expect(env.KV.put).toHaveBeenCalledWith('user:1', expect.any(String))`. Interaction
   assertions are brittle when overused; prefer outcome assertions, and use interaction
   assertions where the outcome is unobservable from the response.
8. **Inject failure modes explicitly.** Because the mock is yours, it can be told to fail:
   `env.KV.failNext('get', new Error('network'))`. Failure injection is the reason mocks
   remain valuable even where Miniflare exists — the real engine does not fail on
   demand. The pool exposes the failure-injection surface uniformly across bindings.
9. **Keep the pool close to the Worker's env shape.** When the Worker's `env` gains a new
   binding, the pool must gain the corresponding mock in the same change. A pool that
   drifts from the real env shape produces tests that pass with a subset of the bindings
   the Worker actually uses.
10. **Type the pool against the Worker's env type.** `createIsolatedEnv(): Env` where
    `Env` is the Worker's generated env type. The type relationship makes drift visible
    at compile time; an untyped pool drifts silently.

A representative pool for a Worker that uses KV and D1:

```ts
import { beforeEach } from 'vitest';
import { MockKV } from './mocks/kv';
import { MockD1 } from './mocks/d1';

export interface Pool {
  KV: MockKV;
  DB: MockD1;
}

export function createIsolatedEnv(): Pool {
  return { KV: new MockKV(), DB: new MockD1() };
}

let env: Pool;
beforeEach(() => { env = createIsolatedEnv(); });
```

Each test receives a fresh `env`; no state crosses the boundary between tests.

## Controls

- The pool is a factory invoked in `beforeEach`; module-level shared mocks are rejected
  in review.
- Each mock implements the full interface of the binding it replaces; the pool's return
  type is checked against the Worker's `Env` type.
- Failure injection is exposed uniformly across bindings and documented.
- The pool's mock set is updated in the same change as the Worker's bindings; a binding
  without a corresponding mock fails type-check.
- Interaction recording is enabled by default and cleared on reset.

## Validation evidence

- Two tests that write to the same KV key through the pool do not observe each other's
  writes; running the file in a different order produces identical results.
- A Worker handler that calls a binding method the mock did not implement fails at
  compile time or at the first call, not in production.
- A test that injects a KV failure observes the Worker's fallback path; removing the
  fallback from the Worker causes the test to fail.
- Adding a binding to the Worker's `env` without updating the pool fails the type check
  in CI.

## Failure modes and correction

- *Module-level shared mock.* Convert to the factory pattern; add a regression test that
  runs two conflicting tests in both orders to demonstrate the coupling.
- *Mock with a subset of the interface.* Add the missing method with the real signature;
  type the mock against the binding's type.
-*Over-elaborate mock reimplementing TTL semantics.* Replace with Miniflare-backed
  binding for the tests that depend on those semantics; keep the mock for logic tests.
- *Reset in module scope instead of `beforeEach`.* Move the reset; verify with a test
  that depends on clean state at the start.
- *Concurrent tests share an instance.* Hand out per-test instances in concurrent mode;
  document the pool's contract.
- *Interaction assertions dominate.* Replace with outcome assertions where the outcome
  is observable; keep interaction assertions for unobservable side effects only.
- *Pool drifts from env shape.* Type the pool's return against `Env`; update both in the
  same change.

## Limitations

- A mock models the semantics you chose to model. Semantics you did not model —
  eventual consistency, size limits, rate limits, cursor pagination edge cases — are
  absent, and tests relying on them pass vacuously.
- Mocks validate the Worker's logic against an assumed contract, not against the real
  engine. Contract drift between the mock and the production binding is detected only
  by integration tests against Miniflare or a deployed preview.
- The pool adds a maintenance surface: every binding change requires a pool change. The
  cost is justified by the isolation and failure-injection benefits, but it is a cost.
- Failure injection through mocks covers code-level failure, not infrastructure-level
  failure. A network partition between the Worker and the storage engine is not
  modelled by an in-memory mock.
- Parallelism across files is safe only because each file constructs its own pool.
  Global singletons outside the pool (a module-level cache, a shared connection) break
  that isolation and are invisible to the pool's design.

## Canonical sources

- Cloudflare, *Vitest integration* (Workers environment configuration, per-test setup,
  and the use of Miniflare-backed bindings in Vitest):
  https://developers.cloudflare.com/workers/testing/vitest-integration/
- Cloudflare, *Vitest integration configuration* (pool and environment options that
  govern isolation between tests):
  https://developers.cloudflare.com/workers/testing/vitest-integration/configuration/
- Cloudflare, *Miniflare* (the real-engine alternative for semantics mocks cannot
  model): https://developers.cloudflare.com/workers/testing/miniflare/
