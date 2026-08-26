# Miniflare Durable Objects Storage Migration Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Durable Object class accumulates state in its key–value storage over months. When you rename
fields, split a single DO into two, or restructure nested JSON blobs, you need confidence that the
migration path (both the one-time data transform and the new read/write paths) is correct before
deploying. The challenge is that `@cloudflare/vitest-pool-workers` does not persist SQLite-backed DO
storage between test runs, so migration tests must manually seed pre-migration data, run the
migration logic, and assert the post-migration shape—all inside a single in-process Miniflare
environment.

---

## Context

Durable Objects use the `DurableObjectStorage` interface. Miniflare (v3+) provides a real
in-process SQLite implementation of that interface. The `@cloudflare/vitest-pool-workers` plugin
exposes `env.DO_NAMESPACE` stubs where `get(id).storage` can be accessed via the
`runInDurableObject` helper, making it possible to write before/after migration test suites
entirely in Vitest without deploying to a live environment.

Migration patterns tested here:
- Field rename (`legacyField` → `newField`)
- Nested document restructure (flat → nested)
- Key prefix change (`item:` → `entry:`)
- Data type coercion (string → number)

---

## Environment Setup

```ts
// vitest.config.ts
import { defineConfig } from "vitest/config";
import { cloudflareWorkersPool } from "@cloudflare/vitest-pool-workers";

export default defineConfig({
  test: {
    pool: cloudflareWorkersPool,
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          durableObjects: {
            COUNTER: "CounterDO",
          },
        },
      },
    },
  },
});
```

```toml
# wrangler.toml
name = "migration-test-worker"
compatibility_date = "2025-01-01"

[[durable_objects.bindings]]
name = "COUNTER"
class_name = "CounterDO"
```

---

## Seeding Pre-Migration State

Use `runInDurableObject` to inject legacy state before any migration code runs:

```ts
// test/do-migration.test.ts
import { env, runInDurableObject } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { CounterDO } from "../src/counter-do";

const STUB_ID = env.COUNTER.idFromName("migration-test");

async function seedLegacyState(stub: DurableObjectStub) {
  await runInDurableObject(stub, async (instance: CounterDO, state) => {
    // Pre-migration shape: flat fields, string count
    await state.storage.put("count", "42");          // was string, should become number
    await state.storage.put("lastUpdated", "2025-01-01T00:00:00Z");
    await state.storage.put("meta_author", "alice"); // old key prefix "meta_"
    await state.storage.put("meta_version", "1");
  });
}

beforeEach(async () => {
  const stub = env.COUNTER.get(STUB_ID);
  await runInDurableObject(stub, async (_instance, state) => {
    await state.storage.deleteAll();
  });
});
```

---

## Testing Field Rename Migration

```ts
describe("field rename: count (string) → value (number)", () => {
  it("migrates legacy 'count' string key to 'value' number key", async () => {
    const stub = env.COUNTER.get(STUB_ID);
    await seedLegacyState(stub);

    // Run migration inside the DO context
    await runInDurableObject(stub, async (_instance, state) => {
      const raw = await state.storage.get<string>("count");
      if (raw !== undefined) {
        await state.storage.put("value", parseInt(raw, 10));
        await state.storage.delete("count");
        await state.storage.put("schemaVersion", 2);
      }
    });

    // Assert post-migration shape
    await runInDurableObject(stub, async (_instance, state) => {
      const value = await state.storage.get<number>("value");
      const count = await state.storage.get<string>("count");
      const version = await state.storage.get<number>("schemaVersion");

      expect(value).toBe(42);
      expect(count).toBeUndefined();
      expect(version).toBe(2);
    });
  });
});
```

---

## Testing Key Prefix Restructure

```ts
describe("key prefix migration: meta_ → cfg:", () => {
  it("rewrites all meta_ keys to cfg: namespace", async () => {
    const stub = env.COUNTER.get(STUB_ID);
    await seedLegacyState(stub);

    await runInDurableObject(stub, async (_instance, state) => {
      const all = await state.storage.list<string>({ prefix: "meta_" });
      const writes: Record<string, string> = {};
      const deletes: string[] = [];

      for (const [key, val] of all) {
        const newKey = key.replace(/^meta_/, "cfg:");
        writes[newKey] = val;
        deletes.push(key);
      }

      await state.storage.put(writes);
      await state.storage.delete(deletes);
    });

    await runInDurableObject(stub, async (_instance, state) => {
      const legacy = await state.storage.list({ prefix: "meta_" });
      const migrated = await state.storage.list({ prefix: "cfg:" });

      expect(legacy.size).toBe(0);
      expect(migrated.get("cfg:author")).toBe("alice");
      expect(migrated.get("cfg:version")).toBe("1");
    });
  });
});
```

---

## Testing Atomic Migration with Rollback Simulation

Durable Object storage supports `transaction()` for atomic writes. Test that a failed migration
leaves storage unchanged:

```ts
describe("atomic migration with rollback", () => {
  it("rolls back partial migration on error", async () => {
    const stub = env.COUNTER.get(STUB_ID);
    await seedLegacyState(stub);

    const snapshotBefore = new Map<string, unknown>();
    await runInDurableObject(stub, async (_instance, state) => {
      const all = await state.storage.list();
      for (const [k, v] of all) snapshotBefore.set(k, v);
    });

    await expect(
      runInDurableObject(stub, async (_instance, state) => {
        await state.storage.transaction(async (txn) => {
          await txn.put("value", 42);
          await txn.delete("count");
          // Simulate error mid-migration
          throw new Error("migration failed");
        });
      })
    ).rejects.toThrow("migration failed");

    // Storage should be unchanged
    await runInDurableObject(stub, async (_instance, state) => {
      const all = await state.storage.list();
      expect(all.size).toBe(snapshotBefore.size);
      for (const [k, v] of snapshotBefore) {
        expect(all.get(k)).toEqual(v);
      }
    });
  });
});
```

---

## Testing `onStart` Migration Guard

Real DOs often gate migration on a stored `schemaVersion`. Test the guard logic:

```ts
describe("schema version guard", () => {
  it("skips migration when schemaVersion is already current", async () => {
    const stub = env.COUNTER.get(STUB_ID);

    // Pre-seed already-migrated state
    await runInDurableObject(stub, async (_instance, state) => {
      await state.storage.put("value", 99);
      await state.storage.put("schemaVersion", 2);
    });

    let migrationRan = false;
    await runInDurableObject(stub, async (_instance, state) => {
      const version = await state.storage.get<number>("schemaVersion");
      if (version === undefined || version < 2) {
        migrationRan = true;
        await state.storage.put("value", 0);
        await state.storage.put("schemaVersion", 2);
      }
    });

    expect(migrationRan).toBe(false);

    await runInDurableObject(stub, async (_instance, state) => {
      expect(await state.storage.get<number>("value")).toBe(99);
    });
  });
});
```

---

## Anti-patterns

- **Deleting all storage then re-running the DO handler** — the DO `fetch` method runs business
  logic, not migration logic. Seed raw storage directly via `runInDurableObject`.
- **Testing migration in isolation from the read path** — always add a follow-up test that reads
  data through the normal DO handler after migration to catch field-name mismatches.
- **Using `idFromString` with a random UUID per test** — multiple IDs create multiple SQLite
  databases; `idFromName("fixed-name")` + `deleteAll()` in `beforeEach` is cheaper and cleaner.
- **Not testing partial-key lists** — `storage.list({ prefix })` is the safe way to find legacy
  keys. Iterating `storage.list()` (no prefix) in tests with seeded extra keys produces flaky
  counts.

---

## Gotchas

- `runInDurableObject` only works when the second type argument matches the exported class. If you
  rename the DO class, update `wrangler.toml` and the pool config together or Miniflare will
  silently use a different namespace.
- `storage.put(record)` (bulk) is atomic in real Workers but Miniflare also honours the atomic
  guarantee—verify your test expectations match that semantic.
- `state.storage.transaction()` throws synchronously if you `await` inside without the `async`
  callback signature. TypeScript catches this but only if the callback return type is correctly
  annotated.
- Miniflare's in-process SQLite is **not** the same physical file across Vitest workers when
  parallelism is enabled. Use `test.concurrent` with distinct `idFromName` seeds to avoid
  cross-worker collisions.

---

## Verification

```bash
# Run only the migration test suite
npx vitest run test/do-migration.test.ts

# Run with verbose output to see each migration step
npx vitest run --reporter=verbose test/do-migration.test.ts

# Confirm no storage leaks between tests (zero-state assertions)
npx vitest run --reporter=verbose --testNamePattern="schema version guard"
```

---

## Related

- `durable-objects-storage-snapshot-testing.md`
- `miniflare-d1-migration-testing.md`
- `vitest-durable-objects-storage-reset-isolation.md`
- `durable-objects-miniflare-fake-timers.md`

---

## Sources

- Cloudflare Durable Objects Storage docs — https://developers.cloudflare.com/durable-objects/api/storage-api/
- `@cloudflare/vitest-pool-workers` README — https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
- Miniflare source: `packages/miniflare/src/workers/durable-objects` in cloudflare/workers-sdk
- Cloudflare blog: "Testing Durable Objects locally with Miniflare" — https://blog.cloudflare.com/miniflare/
