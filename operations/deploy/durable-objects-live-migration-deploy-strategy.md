# Durable Objects Live Migration Deploy Strategy

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
A Cloudflare Durable Object class needs to be migrated to a new class name, a new namespace, or a different storage schema while serving live traffic—without losing state stored in existing DO instances, causing request drops, or forcing a maintenance window.

## Context
Durable Objects are long-lived, globally unique stateful actors tied to a specific class name. Renaming a class or changing its storage schema is not like deploying a stateless Worker—active DO instances hold in-memory state and open WebSocket connections. Cloudflare supports DO migrations via the `[[migrations]]` block in `wrangler.toml`, but applying schema changes to existing instances requires a coordinated deploy strategy: dual-write, lazy migration per instance, and a rollback escape hatch via the old class.

## Migration Types and When to Use Each

| Scenario | Wrangler Migration Type | Risk |
|---|---|---|
| Rename class, preserve IDs | `renamed_classes` | Low — Cloudflare reassigns IDs automatically |
| Move to new namespace | `new_classes` + `deleted_classes` | Medium — existing IDs become invalid |
| Storage schema change | No wrangler migration; code-level lazy migration | High — requires dual-write period |
| Add new DO class | `new_classes` | Low — additive only |

## Wrangler Configuration for Class Rename

```toml
# wrangler.toml
name = "my-worker"
compatibility_date = "2026-08-01"
main = "src/index.ts"

[[durable_objects.bindings]]
name    = "COUNTER"
class_name = "CounterV2"     # new class name

# Migrations: maps old IDs to the new class
[[migrations]]
tag = "v2-rename-counter"
renamed_classes = [
  { from = "Counter", to = "CounterV2" }
]
```

Running `wrangler deploy` with this config atomically reassigns all existing `Counter` instance IDs to `CounterV2`. Existing storage is preserved.

## Storage Schema Migration — Dual-Write Pattern

```typescript
// src/counter-v2.ts
// Lazy per-instance migration: reads old schema, writes new schema on first access.

interface LegacyState {
  count: number;
  // old schema: flat count field
}

interface CurrentState {
  count: number;
  updated_at: string;
  version: number;
  // v2 schema: adds audit fields
}

const SCHEMA_VERSION = 2;

export class CounterV2 implements DurableObject {
  private state: DurableObjectState;
  private env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  private async migrateIfNeeded(): Promise<CurrentState> {
    const stored = await this.state.storage.get<CurrentState>("state");

    if (stored && stored.version === SCHEMA_VERSION) {
      return stored; // Already migrated
    }

    if (stored) {
      // Migrate from whatever version we have
      console.log(`Migrating DO instance from schema v${stored.version ?? 1} to v${SCHEMA_VERSION}`);

      const migrated: CurrentState = {
        count: stored.count ?? 0,
        updated_at: new Date().toISOString(),
        version: SCHEMA_VERSION,
      };

      // Atomic write of migrated state
      await this.state.storage.put("state", migrated);
      return migrated;
    }

    // Brand new instance
    const initial: CurrentState = {
      count: 0,
      updated_at: new Date().toISOString(),
      version: SCHEMA_VERSION,
    };
    await this.state.storage.put("state", initial);
    return initial;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    // Lazy migration on every request (idempotent)
    const current = await this.migrateIfNeeded();

    if (url.pathname === "/increment") {
      const next: CurrentState = {
        count: current.count + 1,
        updated_at: new Date().toISOString(),
        version: SCHEMA_VERSION,
      };
      await this.state.storage.put("state", next);
      return Response.json(next);
    }

    if (url.pathname === "/get") {
      return Response.json(current);
    }

    return new Response("Not Found", { status: 404 });
  }
}

export interface Env {
  COUNTER: DurableObjectNamespace;
}
```

## Rollback Safety: Keeping the Old Class During Migration

```typescript
// src/index.ts — export BOTH classes during the dual-class window
// This allows an instant rollback by reverting wrangler.toml bindings
// without losing any existing DO instances.

export { CounterV2 } from "./counter-v2";
export { Counter } from "./counter-v1"; // Keep old class exportable during migration
```

```toml
# wrangler.toml — dual-class window (temporary)
name = "my-worker"
compatibility_date = "2026-08-01"
main = "src/index.ts"

# Active binding points to new class
[[durable_objects.bindings]]
name       = "COUNTER"
class_name = "CounterV2"

# Old class stays declared so existing IDs remain valid during rollback window
[[durable_objects.bindings]]
name       = "COUNTER_LEGACY"
class_name = "Counter"

[[migrations]]
tag = "v2-rename-counter"
renamed_classes = [{ from = "Counter", to = "CounterV2" }]
```

## Deployment Pipeline

```yaml
# .github/workflows/do-migrate-deploy.yml
name: Durable Objects Migration Deploy

on:
  push:
    branches: [main]
    paths:
      - src/**
      - wrangler.toml

jobs:
  pre-flight:
    name: Migration pre-flight check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci

      - name: Validate migration tag is new
        run: npx tsx scripts/validate-migration-tag.ts
        env:
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          WORKER_NAME: ${{ vars.WORKER_NAME }}

      - name: Dry-run deploy to check metadata
        run: npx wrangler deploy --dry-run --outdir dist/dry-run
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

  deploy:
    name: Deploy with migration
    needs: pre-flight
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci

      - name: Deploy (applies migrations atomically)
        run: npx wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Smoke test DO after migration
        run: npx tsx scripts/do-smoke-test.ts
        env:
          WORKER_URL: ${{ vars.WORKER_URL }}
        timeout-minutes: 3

      - name: Rollback on smoke test failure
        if: failure()
        run: |
          git checkout HEAD~1 -- wrangler.toml src/
          npx wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

```typescript
// scripts/validate-migration-tag.ts
// Confirm the new migration tag hasn't been deployed before (prevents re-applying).
import fs from "node:fs";
import { parse as parseToml } from "smol-toml";

const config = parseToml(fs.readFileSync("wrangler.toml", "utf8")) as {
  migrations?: Array<{ tag: string }>;
};

const localTags = (config.migrations ?? []).map((m) => m.tag);
if (localTags.length === 0) {
  console.log("No migrations declared — skipping validation.");
  process.exit(0);
}

// Fetch deployed migration history
const res = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${process.env.CF_ACCOUNT_ID}` +
    `/workers/scripts/${process.env.WORKER_NAME}`,
  { headers: { Authorization: `Bearer ${process.env.CF_API_TOKEN}` } }
);

if (!res.ok && res.status !== 404) {
  throw new Error(`API error: ${res.status}`);
}

// The deployed_migrations field is available in the script metadata
const json = (await res.json()) as {
  result?: { migration_tag?: string };
};

const deployedTag = json.result?.migration_tag ?? null;
console.log(`Deployed migration tag: ${deployedTag ?? "none"}`);
console.log(`Local migration tags: ${localTags.join(", ")}`);

if (deployedTag && localTags.includes(deployedTag)) {
  // The latest local tag matches what's deployed — this is a re-deploy of same migration
  // That's fine; warn but don't block.
  console.warn("Warning: re-deploying the same migration tag. Ensure this is intentional.");
}

console.log("Migration tag validation passed.");
```

## DO Smoke Test Post-Migration

```typescript
// scripts/do-smoke-test.ts
const BASE = process.env.WORKER_URL!;

// Test a named DO instance that should have pre-existing state
const getId = await fetch(`${BASE}/get`, {
  headers: { "X-DO-Name": "migration-test-instance" },
});

if (!getId.ok) throw new Error(`GET failed: ${getId.status}`);

const state = (await getId.json()) as { count: number; version: number; updated_at: string };
console.log("DO state after migration:", state);

if (state.version !== 2) {
  throw new Error(`Schema migration incomplete: expected version=2, got version=${state.version}`);
}

// Confirm writes still work
const inc = await fetch(`${BASE}/increment`, {
  method: "POST",
  headers: { "X-DO-Name": "migration-test-instance" },
});

if (!inc.ok) throw new Error(`Increment failed: ${inc.status}`);

const incState = (await inc.json()) as { count: number };
if (incState.count !== state.count + 1) {
  throw new Error(`Increment did not work: ${incState.count} !== ${state.count + 1}`);
}

console.log("DO smoke test PASSED.");
```

## Anti-patterns
- Deleting the old DO class from `wrangler.toml` in the same deploy as the schema change — removes the rollback path before migration is verified.
- Using `deleted_classes` in the same migration step as `renamed_classes` — Cloudflare applies migrations atomically; there is no partial rollback.
- Migrating storage schema in `constructor()` rather than request handlers — the constructor runs before storage is accessible in some runtime versions; use `blockConcurrencyWhile` instead.
- Assuming `state.storage.get()` for a missing key returns the old value — after a class rename, storage is migrated in place but the key schema is yours to manage.
- Running DO migrations during a peak-traffic period — migration applies globally and while fast, unusual traffic during the deploy window increases risk of detecting issues too late.

## Gotchas
- Each `[[migrations]]` tag must be unique and is never re-applied; using the same tag for a second migration is silently ignored by Cloudflare.
- Durable Object IDs created before a `renamed_classes` migration remain valid, but IDs created by name (`idFromName`) hash against the new class name — old name-derived IDs no longer resolve.
- `blockConcurrencyWhile(async () => { /* migration */ })` is the correct pattern to serialize the migration within a single DO instance and prevent concurrent request races.
- WebSocket connections to a DO instance are dropped when the Worker script is redeployed; clients must reconnect. Build client-side reconnect logic before migrating WebSocket-heavy DOs.
- Storage limits (128 KB per value, 128 MB total per DO) apply to migrated state; if the old schema stored large values, the new schema must not exceed limits after transformation.

## Verification
1. Create a DO instance via the old class, increment its counter, then deploy the rename migration and confirm the counter value persists.
2. Confirm `wrangler deploy` output includes "Applying migrations" and lists the new tag.
3. Run the DO smoke test script and confirm `version === 2` and `updated_at` is set on a pre-existing instance.
4. Revert `wrangler.toml` to the old binding and redeploy; confirm the instance is still accessible via the legacy class binding.
5. Attempt to use the same migration tag a second time; confirm Cloudflare returns success but no migration is re-applied.

## Related
- `durable-objects-namespace-migration-zero-downtime.md`
- `zero-downtime-database-migrations.md`
- `workers-binding-version-management.md`
- `worker-versioning-gradual-rollout.md`
- `rollback-strategies-workers-pages.md`

## Sources
- https://developers.cloudflare.com/durable-objects/reference/durable-objects-migrations/
- https://developers.cloudflare.com/durable-objects/api/state/#blockConcurrencyWhile
- https://developers.cloudflare.com/durable-objects/best-practices/
