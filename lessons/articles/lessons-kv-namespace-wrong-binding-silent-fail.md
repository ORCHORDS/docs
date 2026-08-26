# KV: Wrong Namespace Binding Causes Silent Data Loss

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Two KV namespaces (`SESSIONS_KV` and `CACHE_KV`) had their bindings swapped in `wrangler.toml` during a refactor. Session writes went to the cache namespace and vice versa. Reads for session data returned `undefined` silently. No runtime error was thrown. Users experienced random logouts and stale cache serving fresh-user responses.

## Context

- Cloudflare Workers + Workers KV
- TypeScript, Wrangler v3
- Two namespaces created in the Cloudflare dashboard with similar names
- Incident discovered 2026-08-15; had been live for ~6 hours before detection
- Detection method: anomaly alert on session creation rate drop + manual key existence check

## Timeline

1. 11:00 UTC — Refactor PR merged; `wrangler.toml` bindings reordered during cleanup
2. 11:03 UTC — Deploy succeeds; no immediate errors
3. 11:05 UTC — Session creation rate drops 40% (users not seeing their new sessions)
4. 11:15 UTC — Cache hit rate spikes unexpectedly (cache namespace now receiving session keys)
5. 14:30 UTC — On-call engineer manually lists keys in both namespaces
6. 14:45 UTC — Root cause identified: namespace IDs swapped in `wrangler.toml`
7. 15:00 UTC — Fix deployed; bindings corrected; affected sessions purged and re-created

## Root Cause

`wrangler.toml` KV namespace bindings are matched by their `id` field (the namespace UUID), not by the binding name. When two `[[kv_namespaces]]` entries have their `id` values swapped, Worker code calling `env.SESSIONS_KV.put()` silently writes to the `CACHE_KV` namespace's underlying storage, and `env.CACHE_KV` reads from session storage. KV never validates that a given binding name maps to any expected namespace.

```toml
# Correct configuration
[[kv_namespaces]]
binding = "SESSIONS_KV"
id     = "aaa111bbb222ccc333ddd444eee555ff"

[[kv_namespaces]]
binding = "CACHE_KV"
id     = "fff555eee444ddd333ccc222bbb111aa"

# What was accidentally deployed (IDs swapped)
[[kv_namespaces]]
binding = "SESSIONS_KV"
id     = "fff555eee444ddd333ccc222bbb111aa"  # ← CACHE_KV namespace ID

[[kv_namespaces]]
binding = "CACHE_KV"
id     = "aaa111bbb222ccc333ddd444eee555ff"  # ← SESSIONS_KV namespace ID
```

## Fix

### Restore correct bindings

```toml
# wrangler.toml — verified correct IDs from Cloudflare dashboard
[[kv_namespaces]]
binding = "SESSIONS_KV"
id     = "aaa111bbb222ccc333ddd444eee555ff"

[[kv_namespaces]]
binding = "CACHE_KV"
id     = "fff555eee444ddd333ccc222bbb111aa"
```

### Purge misrouted keys after restoring bindings

```typescript
// scripts/purge-misrouted-keys.ts
// Run once after fix to remove session keys that landed in CACHE_KV

const CF_ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const CF_API_TOKEN  = process.env.CF_API_TOKEN!;

// CACHE_KV namespace ID (where session keys erroneously landed)
const CACHE_NS_ID = 'fff555eee444ddd333ccc222bbb111aa';

async function listKeys(namespaceId: string, cursor?: string): Promise<{
  keys: { name: string }[];
  cursor?: string;
}> {
  const url = new URL(
    `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces/${namespaceId}/keys`
  );
  if (cursor) url.searchParams.set('cursor', cursor);

  const resp = await fetch(url.toString(), {
    headers: { Authorization: `Bearer ${CF_API_TOKEN}` },
  });
  const json = await resp.json() as any;
  return { keys: json.result, cursor: json.result_info?.cursor };
}

async function deleteKey(namespaceId: string, key: string): Promise<void> {
  await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces/${namespaceId}/values/${encodeURIComponent(key)}`,
    { method: 'DELETE', headers: { Authorization: `Bearer ${CF_API_TOKEN}` } }
  );
}

async function purgeSessionKeysFromCache(): Promise<void> {
  let cursor: string | undefined;
  let purged = 0;

  do {
    const { keys, cursor: next } = await listKeys(CACHE_NS_ID, cursor);
    cursor = next;

    // Session keys follow pattern "session:<userId>:<token>"
    const sessionKeys = keys.filter((k) => k.name.startsWith('session:'));
    await Promise.all(sessionKeys.map((k) => deleteKey(CACHE_NS_ID, k.name)));
    purged += sessionKeys.length;
    console.log(`Purged ${purged} session keys so far...`);
  } while (cursor);

  console.log(`Done. Total purged: ${purged}`);
}

purgeSessionKeysFromCache().catch(console.error);
```

## Prevention

### 1. CI validation script: verify binding IDs match expected values

```typescript
// scripts/validate-kv-bindings.ts — run in CI before deploy
import * as fs from 'fs';
import * as TOML from '@iarna/toml';

// Source of truth: namespace IDs indexed by logical binding name
const EXPECTED: Record<string, string> = {
  SESSIONS_KV: 'aaa111bbb222ccc333ddd444eee555ff',
  CACHE_KV:    'fff555eee444ddd333ccc222bbb111aa',
};

const config = TOML.parse(fs.readFileSync('wrangler.toml', 'utf8')) as any;
const namespaces: Array<{ binding: string; id: string }> = config.kv_namespaces ?? [];

let failed = false;
for (const ns of namespaces) {
  const expected = EXPECTED[ns.binding];
  if (!expected) continue; // unknown binding, skip
  if (ns.id !== expected) {
    console.error(
      `[validate-kv-bindings] MISMATCH: binding=${ns.binding} ` +
      `expected id=${expected} got id=${ns.id}`
    );
    failed = true;
  }
}

if (failed) process.exit(1);
console.log('[validate-kv-bindings] All KV namespace IDs verified OK');
```

### 2. Runtime key-existence smoke test after deploy

```typescript
// src/startup-check.ts — called once on first request after deploy
export async function smokeCheckKVBindings(env: Env): Promise<void> {
  const SENTINEL_SESSION_KEY = '__binding_check_sessions__';
  const SENTINEL_CACHE_KEY   = '__binding_check_cache__';

  // Write a sentinel to SESSIONS_KV
  await env.SESSIONS_KV.put(SENTINEL_SESSION_KEY, '1', { expirationTtl: 60 });

  // It must NOT appear in CACHE_KV (would indicate swapped bindings)
  const leak = await env.CACHE_KV.get(SENTINEL_SESSION_KEY);
  if (leak !== null) {
    // Clean up and hard-fail
    await env.SESSIONS_KV.delete(SENTINEL_SESSION_KEY);
    throw new Error(
      'FATAL: SESSIONS_KV sentinel key found in CACHE_KV — namespace bindings are swapped!'
    );
  }

  await env.SESSIONS_KV.delete(SENTINEL_SESSION_KEY);
}
```

### 3. Add binding names as comments to wrangler.toml

```toml
# wrangler.toml
# KV namespaces — DO NOT reorder without updating the ID comments below
# SESSIONS_KV → namespace "example project-sessions"   (prod) ID: aaa111bbb222ccc333ddd444eee555ff
# CACHE_KV    → namespace "example project-cache"      (prod) ID: fff555eee444ddd333ccc222bbb111aa

[[kv_namespaces]]
binding = "SESSIONS_KV"
id     = "aaa111bbb222ccc333ddd444eee555ff"  # example project-sessions

[[kv_namespaces]]
binding = "CACHE_KV"
id     = "fff555eee444ddd333ccc222bbb111aa"  # example project-cache
```

## Anti-patterns

- Using namespace IDs without inline comments explaining which namespace they represent
- Not pinning expected namespace IDs in a CI validation step
- Assuming KV writes to the wrong namespace will surface as an error (they will not)
- Silently ignoring `undefined` returns from KV without distinguishing "key missing" from "wrong namespace"
- Having similarly-named namespaces (`sessions` vs `session`, `cache` vs `cache-v2`) that are easy to confuse

## Gotchas

- Workers KV `get()` returns `null` for missing keys — this is indistinguishable at runtime from a wrong binding
- The Cloudflare dashboard shows namespace contents per namespace, not per binding; you must cross-reference IDs manually
- Preview (`--local`) environments use local KV stores and will not reproduce this class of mismatch
- `wrangler kv key list --namespace-id <id>` is the fastest way to audit key distribution
- Namespace IDs are stable; they do not change even if you rename the namespace in the dashboard

## Verification

```bash
# List keys in SESSIONS_KV namespace to confirm session keys are present
npx wrangler kv key list --namespace-id aaa111bbb222ccc333ddd444eee555ff

# List keys in CACHE_KV namespace to confirm no session keys leaked
npx wrangler kv key list --namespace-id fff555eee444ddd333ccc222bbb111aa

# Run CI validation script
ts-node scripts/validate-kv-bindings.ts

# Tail Worker to watch for smoke check failures
npx wrangler tail --format pretty 2>&1 | grep -i 'binding_check\|FATAL'
```

## Related

- `lessons-d1-schema-change-rollback-failure.md` — Other misconfiguration-class incidents
- `lessons-workers-fetch-no-abort-signal-hang.md` — Worker runtime failure patterns

## Sources

- https://developers.cloudflare.com/kv/api/
- https://developers.cloudflare.com/workers/wrangler/configuration/#kv-namespaces
- https://developers.cloudflare.com/kv/reference/kv-bindings/
