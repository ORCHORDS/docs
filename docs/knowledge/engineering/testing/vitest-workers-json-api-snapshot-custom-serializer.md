# Vitest Custom Serializers for Workers JSON API Snapshot Testing

2026-08-24 / example.com / production

---

## Symptom / Use-case

Your Cloudflare Workers JSON API returns response bodies with dynamic fields — timestamps, generated IDs, request-correlated trace IDs — that change on every invocation. Standard `toMatchSnapshot()` calls fail on the first re-run because the snapshot records the literal UUID or epoch millisecond. You reach for regex-replace hacks before asserting, losing the structural value of snapshot tests.

The goal: lock the *shape* and *stable content* of JSON API responses while tolerating dynamic fields, without resorting to manual field-by-field assertions that miss regressions on newly added response keys.

---

## Context

Vitest ships with a pluggable snapshot serialization system via `expect.addSnapshotSerializer`. A custom serializer intercepts a value before it is converted to the text stored in the `.snap` file. By defining a serializer that normalises dynamic fields to stable placeholders, you get snapshot diffs that reflect real API contract changes, not clock drift.

This pattern pairs well with `@cloudflare/vitest-pool-workers`, which executes tests inside a real Workers runtime so that `Response.json()`, `Headers`, and `cf` objects serialize faithfully.

The technique applies to:
- REST API endpoints returning JSON with ISO timestamps or auto-increment IDs
- Streaming JSON (NDJSON) where each line is an independent object
- Error envelopes containing request trace IDs
- Paginated responses that embed cursor tokens

---

## Setup

Install the pool and configure Vitest to run inside the Workers runtime.

```ts
// vitest.config.ts
import { defineConfig } from "vitest/config";
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
      },
    },
    setupFiles: ["./test/setup/snapshot-serializers.ts"],
  },
});
```

```toml
# wrangler.toml (minimal)
name = "api-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"
```

---

## Custom Serializer Registration

Register one serializer per dynamic-field category. Keep each serializer focused on a single concern so the `test` predicate stays tight.

```ts
// test/setup/snapshot-serializers.ts
const ISO_DATE_RE =
  /"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z"/g;
const UUID_RE =
  /"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"/gi;
const TRACE_ID_RE = /"[0-9a-f]{32}"/gi;

/** Serializer for plain JS objects destined for JSON snapshot comparison. */
expect.addSnapshotSerializer({
  test(val): val is Record<string, unknown> {
    return val !== null && typeof val === "object" && !Array.isArray(val);
  },
  print(val, serialize) {
    const stable = JSON.parse(
      JSON.stringify(val)
        .replace(ISO_DATE_RE, '"<ISO_DATE>"')
        .replace(UUID_RE, '"<UUID>"')
        .replace(TRACE_ID_RE, '"<TRACE_ID>"'),
    );
    return serialize(stable);
  },
});
```

---

## Testing a JSON API Endpoint

```ts
// test/api/items.snapshot.test.ts
import { env, createExecutionContext, waitOnExecutionContext } from "cloudflare:test";
import { describe, it, expect } from "vitest";
import worker from "../../src/index";

async function fetchJSON(path: string, init?: RequestInit) {
  const ctx = createExecutionContext();
  const res = await worker.fetch(
    new Request(`https://api.example.com${path}`, init),
    env,
    ctx,
  );
  await waitOnExecutionContext(ctx);
  return res.json();
}

describe("GET /items", () => {
  it("returns the expected shape for an empty list", async () => {
    const body = await fetchJSON("/items");
    expect(body).toMatchSnapshot();
  });

  it("returns created item shape on POST", async () => {
    const body = await fetchJSON("/items", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "Widget", price: 9.99 }),
    });
    // id and createdAt are dynamic — serializer normalises them
    expect(body).toMatchSnapshot();
  });
});
```

Resulting snapshot file excerpt — IDs and dates are stable placeholders:

```
// test/api/__snapshots__/items.snapshot.test.ts.snap

exports[`GET /items returns created item shape on POST 1`] = `
{
  "createdAt": "<ISO_DATE>",
  "id": "<UUID>",
  "name": "Widget",
  "price": 9.99,
  "status": "active",
}
`;
```

---

## Inline Snapshots for Error Envelopes

For error responses that rarely change, inline snapshots keep the expected value beside the assertion and make PR diffs self-contained.

```ts
// test/api/errors.snapshot.test.ts
it("returns 422 with structured error envelope", async () => {
  const body = await fetchJSON("/items", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ price: -1 }),
  });

  expect(body).toMatchInlineSnapshot(`
    {
      "code": "VALIDATION_ERROR",
      "details": [
        {
          "field": "name",
          "message": "Required",
        },
        {
          "field": "price",
          "message": "Must be ≥ 0",
        },
      ],
      "requestId": "<TRACE_ID>",
      "status": 422,
    }
  `);
});
```

---

## Serializer for Response Objects

When the test asserts the full `Response` object (headers + body together), extend the serializer to handle `Response` instances.

```ts
// test/setup/snapshot-serializers.ts (additional serializer)
expect.addSnapshotSerializer({
  test(val): val is Response {
    return val instanceof Response;
  },
  async print(val: Response, serialize) {
    const body = await val.clone().json().catch(() => val.clone().text());
    const headers = Object.fromEntries(
      [...val.headers.entries()].filter(
        ([k]) => !["date", "cf-ray"].includes(k),
      ),
    );
    return serialize({ status: val.status, headers, body });
  },
});
```

---

## Anti-patterns

- **Asserting `JSON.stringify(body)` directly** — string comparison hides structural changes behind escape noise; use the object form.
- **Using `toEqual` for the full body** — misses regression when the API adds a new field; snapshot catches additions.
- **One giant serializer that mutates everything** — hard to disable for specific tests; keep serializers granular and composable.
- **Storing dynamic snapshots in CI without `--update-snapshot`** — snapshot files should be committed; CI should fail on unexpected drift, not auto-update.
- **Skipping header assertions** — `Content-Type` mismatches are API contract breaks; include stable headers in the snapshot.

---

## Gotchas

- `toMatchInlineSnapshot` updates the source file in place when run with `vitest --update-snapshot`; ensure the file is writable and not read-only in CI.
- Serializers registered in `setupFiles` run in the pool-workers environment, which is a separate V8 isolate from the Vitest host; confirm your serializer file imports are compatible with the Workers runtime (no Node-only modules).
- `expect.addSnapshotSerializer` is additive across test files — last-registered wins on ties; register in dependency order.
- Snapshot files use `exports[…]` syntax tied to the test name string; renaming a test invalidates its snapshot without warning unless `--update-snapshot` is run.
- The `print` function receives the raw value after `test` returns `true`; if the serializer is async (needed for `Response` bodies), Vitest 2.x supports async `print` — confirm your Vitest version.

---

## Verification

```bash
# Run snapshot tests, fail on new/changed snapshots
npx vitest run --reporter=verbose test/api

# Update snapshots after an intentional API change
npx vitest run --update-snapshot test/api

# Check that all snapshot files are committed
git status --short | grep ".snap"
```

Expected: zero unstaged `.snap` changes in CI after a green run without `--update-snapshot`.

---

## Related

- `snapshot-testing-workers-responses.md` — file-based snapshot patterns for Workers
- `hono-workers-api-snapshot-testing.md` — Hono-specific response snapshot setup
- `vitest-cloudflare-pool-workers.md` — pool-workers environment configuration
- `vitest-custom-matchers-workers-environment.md` — extending `expect` for Workers types
- `api-contract-testing-schema-validation.md` — schema-first validation as a complement

---

## Sources

- Vitest snapshot serializers: https://vitest.dev/guide/snapshot.html#custom-serializer
- `@cloudflare/vitest-pool-workers` docs: https://developers.cloudflare.com/workers/testing/vitest-integration/
- Vitest inline snapshot update workflow: https://vitest.dev/guide/snapshot.html#updating-snapshots
