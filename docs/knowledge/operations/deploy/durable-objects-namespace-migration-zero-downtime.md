# Durable Objects Namespace Migration — Zero-Downtime Versioning

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You need to change a Durable Object class — rename it, restructure its storage schema, split it into two classes, or migrate it to a new script — without dropping active connections or losing existing object state. Unlike a stateless Worker, a Durable Object binds its name/ID directly to a class definition; changing the class binding naively orphans every existing object.

Common triggers:

- Renaming a class during a refactor breaks all `env.MY_DO.idFromName()` lookups that reference the old binding name.
- A schema change (new storage key layout, compressed value format) must be applied to thousands of existing objects individually — there is no `ALTER TABLE`.
- A monorepo extraction moves a DO class from `worker-a` to `worker-b`, but objects already live in `worker-a`'s namespace.

## Context

Durable Objects store their state in Cloudflare's globally replicated storage tied to a namespace UUID that is generated when the binding is first deployed. The DO namespace is separate from the Worker script: you can update the script while keeping the same namespace UUID by preserving the `[[durable_objects]]` binding name and `class_name`. If either changes, Cloudflare creates a new namespace and old objects become inaccessible through the new binding.

The `new_sqlite_classes` / `new_classes` migration mechanism in `wrangler.toml` lets you tell Cloudflare how to rename a class without creating a new namespace, or how to transfer a class between scripts.

Cloudflare DO storage per object is bounded to 128 KiB of data returned per `list()` call; large objects often paginate. A migration that reads and rewrites every key must account for this pagination or it silently stops mid-object.

## Step 1 — Understand migration types in wrangler.toml

Wrangler's `[[migrations]]` table describes class-level transitions to the Cloudflare API at deploy time. Each entry is appended in order; they run once and are not re-run.

```toml
# wrangler.toml

name = "orchords-api"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[durable_objects.bindings]]
name = "ROOM"          # env.ROOM inside the Worker
class_name = "RoomV2"  # the TypeScript class name in your script

[[migrations]]
tag = "v1"
new_sqlite_classes = ["RoomV1"]   # initial creation

[[migrations]]
tag = "v2"
renamed_classes = [
  { from = "RoomV1", to = "RoomV2" }
]
# RoomV2 keeps the same namespace UUID; existing objects keep their storage
```

Key rules:
- `tag` must be unique and must not be reused or reordered.
- `new_sqlite_classes` creates a namespace for a brand-new class with SQLite storage (preferred for new classes as of 2025).
- `renamed_classes` renames a class within the **same script** — same namespace, same objects, new TypeScript class name.
- `transferred_classes` moves a class from another script into this one. Requires the source script to have already deployed the same object.

## Step 2 — Rename a class (same script, no state change)

This is the simplest migration — a pure TypeScript rename. You want `RoomV1` to be called `RoomV2` in code without any storage changes.

```toml
# Before:
[[migrations]]
tag = "v1"
new_sqlite_classes = ["RoomV1"]

# After (add, never edit the existing entry):
[[migrations]]
tag = "v1"
new_sqlite_classes = ["RoomV1"]

[[migrations]]
tag = "v2"
renamed_classes = [{ from = "RoomV1", to = "RoomV2" }]
```

```typescript
// src/room.ts — rename only, no storage changes
export class RoomV2 implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const count = (await this.state.storage.get<number>("count")) ?? 0;
    return new Response(JSON.stringify({ count }), {
      headers: { "Content-Type": "application/json" },
    });
  }
}
```

Deploy once: `wrangler deploy`. The migration runs server-side. No request downtime; objects that were asleep stay asleep with all their storage intact. Objects handling live WebSocket connections continue uninterrupted because the migration does not evict running instances.

## Step 3 — Schema migration inside an object (lazy upgrade)

When you change the storage layout (e.g., splitting a single `"data"` key into granular keys), you cannot migrate all objects in a single deploy — there is no global "run this for every object" API. The accepted pattern is **lazy upgrade on first access**.

```typescript
export class RoomV2 implements DurableObject {
  private state: DurableObjectState;
  private readonly SCHEMA_VERSION = 2;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    // blockConcurrencyWhile runs before any fetch is handled
    this.state.blockConcurrencyWhile(async () => {
      await this.migrateIfNeeded();
    });
  }

  private async migrateIfNeeded(): Promise<void> {
    const version = (await this.state.storage.get<number>("_schema_version")) ?? 1;
    if (version >= this.SCHEMA_VERSION) return;

    if (version === 1) {
      // v1 stored everything in a single JSON blob under "data"
      const blob = await this.state.storage.get<Record<string, unknown>>("data");
      if (blob) {
        // Write granular keys
        const entries = Object.entries(blob).map(([k, v]) => [`field:${k}`, v]);
        await this.state.storage.put(Object.fromEntries(entries));
        await this.state.storage.delete("data");
      }
    }

    await this.state.storage.put("_schema_version", this.SCHEMA_VERSION);
  }

  async fetch(request: Request): Promise<Response> {
    // All reads here see v2 layout
    const url = new URL(request.url);
    const field = url.searchParams.get("field") ?? "name";
    const value = await this.state.storage.get<string>(`field:${field}`);
    return new Response(JSON.stringify({ [field]: value ?? null }));
  }
}
```

`blockConcurrencyWhile` ensures the migration finishes before any `fetch` call is dispatched. If the object crashes during migration, the next wake retries from the same state — make each migration step idempotent.

## Step 4 — Transfer a class between scripts (monorepo extraction)

When moving a DO class from `worker-a` to `worker-b` in a monorepo:

```toml
# worker-b/wrangler.toml

[[durable_objects.bindings]]
name = "ROOM"
class_name = "RoomV2"
script_name = ""   # empty = local script (this Worker)

[[migrations]]
tag = "v1"
new_sqlite_classes = ["RoomV2"]  # placeholder — will be overwritten by transfer

[[migrations]]
tag = "v2-transfer"
transferred_classes = [
  {
    from = "RoomV1",
    from_script = "worker-a",
    to = "RoomV2"
  }
]
```

**Deploy order matters:**
1. Deploy `worker-a` first with `RoomV1` still present (do not remove it yet).
2. Deploy `worker-b` with the `transferred_classes` migration.
3. Verify objects resolve correctly through `worker-b`'s binding.
4. Remove `RoomV1` from `worker-a` in a subsequent deploy.

## Step 5 — GitHub Actions pipeline

```yaml
# .github/workflows/deploy-do-migration.yml
name: Deploy with DO Migration

on:
  push:
    branches: [main]
    paths:
      - "worker-b/**"

jobs:
  migrate-and-deploy:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"

      - run: npm ci

      # Deploy source script first so transfer source is valid
      - name: Deploy worker-a (source, keeping old class)
        working-directory: worker-a
        run: npx wrangler deploy --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Deploy worker-b (with transfer migration)
        working-directory: worker-b
        run: npx wrangler deploy --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Smoke test DO resolution
        run: |
          STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
            "https://worker-b.orchords.workers.dev/room/healthcheck")
          [ "$STATUS" = "200" ] || (echo "DO smoke test failed: $STATUS" && exit 1)
```

## Anti-patterns

- **Editing an existing migration tag**: Wrangler tracks which tags have been applied per-account. Editing a tag that already ran has no effect on existing namespaces but creates a divergence between your config and reality.
- **Removing a class from the binding before transferring it**: The transfer source must exist in `worker-a` at the time of the transfer deploy. Removing it first orphans the migration.
- **Running a full-scan migration on deploy**: Iterating over every DO object from a Worker or Cron Trigger on deploy day blocks and scales with object count. Use lazy upgrade instead.
- **Assuming `blockConcurrencyWhile` is optional for schema upgrades**: Without it, a concurrent request can read a half-migrated storage state.
- **Forgetting to paginate `storage.list()`**: The default `limit` is 128 entries. Large objects with many keys need `{ cursor }` iteration or data is silently lost.

## Gotchas

- `renamed_classes` only works within the same script. Cross-script renames require `transferred_classes`.
- SQLite-backed DOs (`new_sqlite_classes`) and KV-backed DOs (`new_classes`) cannot be interconverted via migration — this requires a new namespace and a data copy at the application level.
- Objects that have never been activated (never received a request) are migrated lazily — they do not appear in any inventory and cannot be pre-migrated.
- The `from_script` name in `transferred_classes` is the `name` field in the source Worker's `wrangler.toml`, not the class name.
- Cloudflare imposes a hard limit of 1,000 migrations per namespace. Long-lived projects should periodically squash old migration entries by rebuilding the namespace with a fresh `new_sqlite_classes` entry and migrating data at the application level.

## Verification

```bash
# Confirm migration tags that have been applied to an account namespace
npx wrangler durableObjects namespaces list

# Tail live DO activity post-deploy
npx wrangler tail --env production --format pretty | grep "RoomV2"

# Manually trigger a specific DO to force lazy migration
curl "https://worker-b.orchords.workers.dev/room/ping?id=known-test-id"
```

Check Cloudflare dashboard under Workers > Durable Objects > the namespace > Metrics for error counts and alarm counts spiking in the first 15 minutes after deploy.

## Related

- `workers-secrets-rotation-zero-downtime.md`
- `zero-downtime-database-migrations.md`
- `rollback-strategies-workers-pages.md`
- `worker-versioning-gradual-rollout.md`
- `blue-green-deploy-cloudflare-workers.md`

## Sources

- Cloudflare Durable Objects migration docs: https://developers.cloudflare.com/durable-objects/reference/durable-objects-migrations/
- Cloudflare Durable Objects storage API: https://developers.cloudflare.com/durable-objects/api/storage-api/
- `blockConcurrencyWhile` reference: https://developers.cloudflare.com/durable-objects/api/state/
