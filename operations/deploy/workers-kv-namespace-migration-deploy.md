# Workers KV Namespace Migration Deploy

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You need to rename a Workers KV namespace, restructure its key schema, or split one namespace into multiple during a zero-downtime deploy. Swapping the `wrangler.toml` binding in one step causes a brief window where the Worker reads an empty namespace or stale keys, resulting in cache misses, missing config, or broken feature flags.

## Context

Cloudflare Workers KV namespaces are referenced by binding name in `wrangler.toml`. Changing the binding (pointing to a new namespace ID) takes effect on the next `wrangler deploy`. There is no built-in migration primitive — you must coordinate data replication and binding swap across deployment versions manually. The pattern mirrors blue-green deploys but applied to a key-value store rather than compute.

---

## 1. Dual-Write During Transition

Add a wrapper that writes to both the old and new namespace during the migration window. The Worker reads from the new namespace with a fallback to the old one.

```typescript
// src/kv-migration-adapter.ts
export class KVMigrationAdapter {
  constructor(
    private readonly oldNS: KVNamespace,
    private readonly newNS: KVNamespace,
    private readonly migrating: boolean
  ) {}

  async get(key: string): Promise<string | null> {
    const value = await this.newNS.get(key);
    if (value !== null) return value;
    if (this.migrating) return this.oldNS.get(key);
    return null;
  }

  async put(key: string, value: string, options?: KVNamespacePutOptions): Promise<void> {
    await this.newNS.put(key, value, options);
    if (this.migrating) {
      await this.oldNS.put(key, value, options);
    }
  }
}
```

```typescript
// src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const isMigrating = (await env.CONFIG.get('kv_migration_active')) === 'true';
    const kv = new KVMigrationAdapter(env.OLD_NAMESPACE, env.NEW_NAMESPACE, isMigrating);
    // use kv instead of env.OLD_NAMESPACE directly
    const value = await kv.get('my-key');
    return new Response(value ?? 'not found');
  },
};
```

---

## 2. Background Migration Worker (Cron-Triggered)

Copy keys from the old namespace to the new one using a scheduled Worker. Use cursor-based pagination to handle large namespaces safely.

```typescript
// src/migration-worker.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    let cursor: string | undefined;
    let migrated = 0;
    const BATCH_SIZE = 100;

    do {
      const list = await env.OLD_NAMESPACE.list({ limit: BATCH_SIZE, cursor });
      cursor = list.cursor;

      await Promise.all(
        list.keys.map(async ({ name, expiration }) => {
          const value = await env.OLD_NAMESPACE.get(name);
          if (value !== null) {
            await env.NEW_NAMESPACE.put(name, value, expiration ? { expiration } : undefined);
            migrated++;
          }
        })
      );
    } while (!list.list_complete);

    await env.CONFIG.put('kv_migration_keys_copied', String(migrated));
    console.log(`KV migration: copied ${migrated} keys`);
  },
};
```

---

## 3. Namespace Binding Swap in wrangler.toml

After data is fully replicated, swap the binding in a single deploy. Keep the old binding available under an `_LEGACY` alias for one release cycle.

```toml
# wrangler.toml — during migration
[[kv_namespaces]]
binding = "OLD_NAMESPACE"
id = "aaaa1111bbbb2222cccc3333dddd4444"

[[kv_namespaces]]
binding = "NEW_NAMESPACE"
id = "zzzz9999yyyy8888xxxx7777wwww6666"
```

```toml
# wrangler.toml — after cutover (rename OLD to legacy alias)
[[kv_namespaces]]
binding = "NEW_NAMESPACE"
id = "zzzz9999yyyy8888xxxx7777wwww6666"

[[kv_namespaces]]
binding = "OLD_NAMESPACE_LEGACY"
id = "aaaa1111bbbb2222cccc3333dddd4444"
```

---

## 4. Migration Gate in CI Pipeline

Block the namespace binding swap deploy until the background migration confirms all keys are present.

```typescript
// scripts/check-kv-migration.ts
const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const API_TOKEN  = process.env.CF_API_TOKEN!;
const OLD_NS_ID  = process.env.OLD_KV_NAMESPACE_ID!;
const NEW_NS_ID  = process.env.NEW_KV_NAMESPACE_ID!;

async function countKeys(nsId: string): Promise<number> {
  const url = `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/storage/kv/namespaces/${nsId}/keys?limit=1000`;
  const res = await fetch(url, { headers: { Authorization: `Bearer ${API_TOKEN}` } });
  const json = await res.json() as { result_info: { count: number } };
  return json.result_info.count;
}

const oldCount = await countKeys(OLD_NS_ID);
const newCount = await countKeys(NEW_NS_ID);

if (newCount < oldCount) {
  console.error(`Migration incomplete: old=${oldCount} new=${newCount}`);
  process.exit(1);
}

console.log(`KV migration verified: ${newCount} keys present in new namespace`);
```

---

## 5. Post-Cutover Validation Worker

After the binding swap deploy, run a smoke-check to confirm reads from the new namespace succeed for known sentinel keys.

```typescript
// scripts/validate-kv-cutover.ts
const WORKER_URL = process.env.WORKER_URL!;
const SENTINEL_KEYS = ['config/feature-flags', 'config/rate-limits', 'config/api-version'];

for (const key of SENTINEL_KEYS) {
  const res = await fetch(`${WORKER_URL}/__kv-probe?key=<redacted-secret>
  if (!res.ok) {
    throw new Error(`Sentinel key "${key}" not found after KV cutover`);
  }
  console.log(`OK: ${key}`);
}
```

---

## Anti-Patterns

- **Swapping bindings before data is copied** — causes a cold-namespace window where all reads return `null`.
- **Deleting the old namespace immediately after cutover** — removes the rollback option; retain it for at least 48 hours.
- **Using `list()` without cursor pagination** — silently truncates at 1,000 keys; large namespaces appear fully migrated when they are not.
- **Writing only to the new namespace during dual-write** — old-namespace reads by un-deployed Workers will miss new writes.

## Gotchas

- KV `expiration` values are Unix timestamps; copying them verbatim from `oldNS.list()` keys preserves original TTLs rather than resetting them. Verify this is the desired behavior.
- The Workers free tier limits KV write operations per day. Large namespace migrations should be batched over multiple cron invocations.
- `wrangler kv:bulk put` is available for seeding namespaces from a JSON file during initial migration, bypassing per-write rate limits.
- KV consistency is eventual; allow 60 seconds after a bulk copy before verifying counts via the REST API.

## Verification

1. Run `wrangler kv:key list --namespace-id=<new-id> | wc -l` and compare against old namespace count.
2. Deploy smoke-check Worker script against staging; confirm all sentinel keys resolve.
3. Enable `kv_migration_active=false` via KV config key to disable dual-write, then monitor error rates for 5 minutes.
4. Check Worker logs with `wrangler tail` for any `null` reads that indicate missing keys.

## Related

- `feature-flag-deployment-gates-cloudflare-kv.md`
- `workers-binding-version-management.md`
- `zero-downtime-r2-bucket-migration.md`
- `deployment-health-gates-automated-rollback.md`

## Sources

- https://developers.cloudflare.com/kv/api/
- https://developers.cloudflare.com/kv/reference/kv-bindings/
- https://developers.cloudflare.com/workers/wrangler/commands/#kv-bulk
- https://developers.cloudflare.com/kv/reference/consistency/
