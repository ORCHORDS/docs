# test-isolation-principles

**Issue:** Ensuring tests do not affect each other's outcome through shared state
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Tests pass when run individually but fail when the whole suite runs, or fail only in a specific order, indicating hidden shared state.

## Pattern / Solution
Each test must own its complete lifecycle:

- **Arrange inside the test or in `beforeEach`** — never in a `beforeAll` that is mutated.
- **Clean up in `afterEach`** — reset mocks, databases, and module registries.
- **Avoid module-level singletons** — prefer factory functions that return fresh instances.

```ts
beforeEach(() => {
  vi.clearAllMocks();           // reset all mock call counts
  db.reset();                   // clear in-memory DB
});

afterEach(() => {
  vi.restoreAllMocks();         // restore any spied-on originals
});
```

For file-system tests, use a unique temp directory per test:

```ts
const dir = await fs.mkdtemp(path.join(os.tmpdir(), "test-"));
afterEach(() => fs.rm(dir, { recursive: true }));
```

## Gotchas
- `beforeAll` shared setup is fine for read-only resources (schema creation); never for mutable state.
- Snapshot files shared across tests can cause ordering issues — prefer per-test snapshot files.
- Module caches (`require.cache`) must be cleared if modules have side effects.

## Related
- test-independence
- shared-test-state-antipatterns
- flaky-test-remediation
