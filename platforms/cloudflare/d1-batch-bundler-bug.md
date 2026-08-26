# D1 batch failures: verify the prepared-statement input before blaming the bundler

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** corrected and documented

## Problem

A production bundle appears to accept a D1 `batch()` call but writes no rows,
while sequential `prepare().bind().run()` calls work. It is tempting to infer
that Wrangler or the Pages Functions bundler stripped SQL from valid prepared
statements.

That conclusion is not supported until the deployed code is shown to pass
actual `D1PreparedStatement` objects. A cast can hide an unsupported runtime
shape:

```ts
// Unsupported. A type assertion does not turn records into prepared statements.
const records = [
  { sql: 'INSERT INTO jobs (id) VALUES (?)', params: ['job-1'] },
] as unknown as D1PreparedStatement[];

await env.DB.batch(records);
```

A failure of this shape is evidence about the cast records, not evidence that
`env.DB.prepare(sql).bind(...)` was damaged by bundling.

## Verified platform contract

Cloudflare documents `D1Database.prepare()` as returning a
`D1PreparedStatement`. `D1Database.batch()` takes an array of those prepared
statements, executes them sequentially in one call, and treats the batch as a
SQL transaction. If a statement fails, D1 aborts or rolls back the sequence.

Use the binding API directly:

```ts
const statements = rows.map((row) =>
  env.DB
    .prepare('INSERT INTO jobs (id, payload) VALUES (?, ?)')
    .bind(row.id, JSON.stringify(row.payload)),
);

const results = await env.DB.batch(statements);
```

Pages Functions D1 bindings expose this same Workers Binding API. Do not build
a parallel object protocol and cast it to the platform type.

## Controls

- Keep SQL creation at the `prepare()` boundary; retain the returned object
  through `bind()` and into `batch()`.
- Ban `as unknown as D1PreparedStatement` and raw `{ sql, params }` batch
  adapters in review and static checks.
- Treat required writes as required. Do not use `INSERT OR IGNORE` where a
  zero-row result would violate an invariant or prevent rollback.
- Pin Wrangler, workerd/Miniflare, compatibility date, and Workers types in
  diagnostic evidence.
- Test the same built artifact and binding configuration used by the candidate
  deployment against a disposable D1 database.
- Keep parameterized user DML on prepared statements. Cloudflare describes
  `exec()` as less safe and intended for maintenance or one-shot work.

## Rollback verification

A source-shape test is not enough. Use a real Workers/D1 test:

1. Create the tables and constraints in an isolated database.
2. Install a deterministic trigger or constraint that fails statement two.
3. Call the production function with a prepared-statement batch.
4. Assert that statement one left no row.
5. Repeat with a failure in the last required statement.
6. Run the success case and verify result ordering and every invariant.
7. Build the deploy artifact with the pinned Wrangler version and repeat the
   failure test in a guarded non-production environment.

If the supported shape still fails only after bundling, preserve the smallest
reproduction, exact artifact SHA, tool versions, compatibility date, and
non-sensitive error. File that evidence with Cloudflare before publishing a
general platform workaround.

## Gotchas

- TypeScript assertions provide no runtime conversion or validation.
- A local mock that accepts arbitrary records can conceal a production input
  mismatch; prefer the Cloudflare Workers Vitest integration and real bindings.
- Sequential `.run()` calls remove transaction rollback and can leave partial
  state even when they appear to fix an unsupported batch input.
- A Durable Object can serialize callers but does not make writes to an
  external D1 database atomic.
- `batch()` rollback covers only statements inside the batch. Session
  creation, audit publication, or external side effects afterward still need
  idempotent recovery.
- Do not claim a silent bundler defect from one unsupported experiment.

## Verification checklist

- [ ] Every batch element originates from `DB.prepare(...).bind(...)`.
- [ ] No raw record is cast to `D1PreparedStatement`.
- [ ] Failure at each required write rolls all earlier batch writes back.
- [ ] Ignored conflicts cannot hide a missing required row.
- [ ] The production-built artifact is exercised against disposable D1.
- [ ] Evidence records exact source SHA and runtime/tool versions.
- [ ] Retry and post-transaction failure behavior is defined separately.

## Official sources

- Cloudflare D1 Database API — `prepare()`, `batch()`, transactional rollback,
  and `exec()` guidance:
  https://developers.cloudflare.com/d1/worker-api/d1-database/
- Cloudflare Pages Functions bindings — D1 uses the Workers Binding API:
  https://developers.cloudflare.com/pages/functions/bindings/#d1-databases
- Cloudflare Workers testing:
  https://developers.cloudflare.com/workers/testing/
- Cloudflare Vitest integration test APIs:
  https://developers.cloudflare.com/workers/testing/vitest-integration/test-apis/
