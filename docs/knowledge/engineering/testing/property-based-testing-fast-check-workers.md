# Property-Based Testing with fast-check for Workers Edge Cases

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Unit tests for example project Workers pass on carefully chosen examples but fail in production on unexpected Unicode track titles, zero-byte payloads, or extremely large page-size parameters. Manual example enumeration cannot cover the combinatorial space of inputs a real mobile client or API consumer will send.

## Context

fast-check is a TypeScript-native property-based testing library compatible with vitest and jest. It generates hundreds of random inputs per property, then automatically shrinks failing cases to the minimal reproducible example. example project uses it to test Workers request handlers, D1 query builders, and mobile payload serialisation without enumerating every edge case manually.

Version: `fast-check` 3.x, `vitest` 2.x, Miniflare 3.x for Workers runtime emulation.

## Core Concepts

| Concept      | fast-check term  | Meaning                                              |
|--------------|------------------|------------------------------------------------------|
| Arbitrary    | `fc.string()`    | Generator for a type of input                        |
| Property     | `fc.assert()`    | A predicate that must hold for all generated inputs  |
| Shrinking    | automatic        | Reducing a failing input to the smallest case        |
| Seed         | `fc.assert(..., { seed })` | Reproducible replay of a failure         |
| Num runs     | `numRuns: 1000`  | How many random samples per property                 |

## Basic Workers Handler Property

```typescript
// tests/properties/tracks-handler.property.ts
import fc from "fast-check";
import { describe, it } from "vitest";
import { handleTracksRequest } from "../../src/handlers/tracks";

describe("GET /api/tracks property", () => {
  it("always returns JSON with status 200 for any valid page param", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.integer({ min: 1, max: 500 }),   // page
        fc.integer({ min: 1, max: 100 }),   // pageSize
        async (page, pageSize) => {
          const req = new Request(
            `https://api.example.com/api/tracks?page=${page}&pageSize=${pageSize}`
          );
          const res = await handleTracksRequest(req, mockEnv());
          expect(res.status).toBe(200);
          const body = await res.json();
          expect(Array.isArray(body.items)).toBe(true);
          expect(body.total).toBeGreaterThanOrEqual(0);
        }
      ),
      { numRuns: 200 }
    );
  });
});
```

## Input Shrinking in Practice

When fast-check finds a failing case it shrinks automatically:

```typescript
it("sanitises track title before D1 insert", async () => {
  await fc.assert(
    fc.asyncProperty(
      fc.string({ minLength: 0, maxLength: 512 }),
      async (title) => {
        const sanitised = sanitiseTitle(title);
        // property: sanitised title never contains SQL meta-characters
        expect(sanitised).not.toMatch(/['";\\]/);
        // property: sanitised title length <= original
        expect(sanitised.length).toBeLessThanOrEqual(title.length);
      }
    ),
    { numRuns: 500, verbose: true }
  );
});
```

On failure, output includes the minimal failing string and a seed:

```
Property failed after 1 tests
{ seed: 1234567890, path: "0:1", endOnFailure: true }
Counterexample: ["it's alive"]
```

Replay with:

```bash
vitest --reporter=verbose -- --seed=1234567890
```

## D1 Query Invariants

Properties for query builder correctness — run against Miniflare local D1:

```typescript
// tests/properties/d1-query.property.ts
import fc from "fast-check";
import { Miniflare } from "miniflare";
import { buildTrackQuery } from "../../src/db/queries";

let mf: Miniflare;

beforeAll(async () => {
  mf = new Miniflare({ modules: true, d1Databases: ["DB"] });
  await seedFixtureTracks(mf, 100);
});
afterAll(() => mf.dispose());

const filterArb = fc.record({
  genre:    fc.option(fc.constantFrom("electronic", "jazz", "folk"), { nil: undefined }),
  minBpm:   fc.option(fc.integer({ min: 60, max: 200 }), { nil: undefined }),
  maxBpm:   fc.option(fc.integer({ min: 60, max: 200 }), { nil: undefined }),
});

it("query result count is always <= total fixture count", async () => {
  const db = await mf.getD1Database("DB");
  await fc.assert(
    fc.asyncProperty(filterArb, async (filters) => {
      const rows = await buildTrackQuery(db, filters);
      expect(rows.length).toBeLessThanOrEqual(100);
    }),
    { numRuns: 300 }
  );
});

it("minBpm/maxBpm filter never returns out-of-range tracks", async () => {
  const db = await mf.getD1Database("DB");
  await fc.assert(
    fc.asyncProperty(
      fc.integer({ min: 60, max: 180 }),
      fc.integer({ min: 60, max: 180 }),
      async (minBpm, maxBpm) => {
        fc.pre(minBpm <= maxBpm); // precondition: valid range
        const rows = await buildTrackQuery(db, { minBpm, maxBpm });
        for (const row of rows) {
          expect(row.bpm).toBeGreaterThanOrEqual(minBpm);
          expect(row.bpm).toBeLessThanOrEqual(maxBpm);
        }
      }
    ),
    { numRuns: 200 }
  );
});
```

`fc.pre()` discards samples that violate a precondition without counting them as failures.

## Mobile Payload Fuzzing

Mobile clients POST JSON payloads; use fast-check to verify the Worker never 500s on malformed input:

```typescript
// tests/properties/upload-payload.property.ts
const payloadArb = fc.oneof(
  fc.record({
    title:    fc.string({ minLength: 1, maxLength: 200 }),
    durationMs: fc.integer({ min: 0, max: 3_600_000 }),
    mimeType: fc.constantFrom("audio/mpeg", "audio/wav", "audio/flac"),
  }),
  fc.anything(),          // fully arbitrary — includes non-objects
  fc.string(),            // plain string body
  fc.constant(null),
  fc.constant(undefined),
);

it("POST /api/tracks never returns 500 for any payload shape", async () => {
  await fc.assert(
    fc.asyncProperty(payloadArb, async (payload) => {
      const body = payload === undefined ? undefined : JSON.stringify(payload);
      const req = new Request("https://api.example.com/api/tracks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
      });
      const res = await handleUploadRequest(req, mockEnv());
      expect(res.status).not.toBe(500);
    }),
    { numRuns: 500 }
  );
});
```

| Scenario           | Arbitrary used          | Property asserted            |
|--------------------|-------------------------|------------------------------|
| Valid payload       | `fc.record({...})`      | status 201                   |
| Arbitrary value     | `fc.anything()`         | status not 500               |
| Null body           | `fc.constant(null)`     | status 400 (validation error)|
| Giant string        | `fc.string({ maxLength: 100_000 })` | status not 500  |

## Anti-patterns

- Writing properties that only test the happy path (`expect(result).toBeDefined()`) — too weak to catch real invariant violations.
- Using `fc.anything()` without `fc.pre()` guards when the handler legitimately throws on bad content-type — test becomes noisy.
- Setting `numRuns` to 10 to speed up CI — defeats the purpose; use `--runInBand` and keep numRuns >= 100 for handlers.
- Not fixing the seed when debugging — re-running without `{ seed }` generates a different counterexample each time.
- Mutating shared Miniflare D1 state inside an `asyncProperty` without resetting between iterations — properties must be independent.

## Gotchas

- `fc.pre()` throws `PreconditionFailure` which fast-check catches internally; do not catch it yourself or properties stop filtering.
- Async properties require `fc.asyncProperty`, not `fc.property` — passing an async function to `fc.property` silently passes every run.
- Miniflare D1 in-memory state persists across `asyncProperty` iterations; reset with `DELETE FROM` in `beforeEach` if writes occur.
- fast-check 3.x changed `fc.option` default nil from `null` to `undefined`; update matchers accordingly.
- `vitest` runs properties in the same process; Workers globals (`Request`, `Response`, `Headers`) must be polyfilled or use `@cloudflare/workers-types`.

## Verification

```bash
# Run all property tests with verbose output
npx vitest run --reporter=verbose tests/properties/

# Replay a specific failing seed
FAST_CHECK_SEED=1234567890 npx vitest run tests/properties/d1-query.property.ts

# Increase runs for nightly CI
FAST_CHECK_NUM_RUNS=2000 npx vitest run tests/properties/
```

Confirm shrinking is working:

```bash
# Introduce a deliberate bug in sanitiseTitle, then run:
npx vitest run tests/properties/tracks-handler.property.ts
# Output should show Counterexample reduced to shortest failing string
```

## Related

- `property-based-testing-fast-check.md`
- `property-based-testing.md`
- `fuzz-testing-basics.md`
- `miniflare-d1-integration-testing.md`
- `d1-test-fixtures-wrangler-seed.md`
- `workers-unit-testing-fetch-mocking.md`

## Sources

- https://fast-check.dev/docs/core-blocks/arbitraries/
- https://fast-check.dev/docs/configuration/runner-parameters/
- https://miniflare.dev/storage/d1
- https://developers.cloudflare.com/workers/testing/vitest-integration/
