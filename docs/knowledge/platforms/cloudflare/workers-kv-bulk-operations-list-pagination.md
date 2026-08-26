# Workers KV Bulk Operations and List Pagination

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

You need to enumerate every key in a KV namespace to build a sitemap, prune stale entries, migrate data to D1, or audit usage. The naive loop using `list()` without a cursor stalls at 1 000 keys. You also want to bulk-write hundreds of key-value pairs at once from a Wrangler script or a Worker handler, and you want to understand the ceiling before you hit it at runtime.

---

## Context

Workers KV exposes four primitives: `get`, `put`, `delete`, and `list`. The `list` method is the only way to enumerate keys, but it returns at most **1 000 keys per call** and uses an opaque cursor for pagination. Cloudflare does not expose a native batch `get` or `delete` at the **Workers runtime** level — bulk operations exist only through the **REST API** or **Wrangler CLI**. Understanding which surface handles bulk work, and how to paginate `list` correctly, is the core skill covered here.

### Key limits (as of 2025)

| Operation | Limit |
|-----------|-------|
| `list()` page size | 1 000 keys max (`limit` param) |
| `put()` value size | 25 MiB |
| Metadata per key | 1 024 bytes (JSON) |
| Keys per namespace | Unlimited (effectively) |
| REST bulk write batch | 10 000 key-value pairs per request |
| REST bulk delete batch | 10 000 keys per request |

---

## Paginating `list()` Correctly

`list()` returns `{ keys, list_complete, cursor }`. When `list_complete` is `false`, pass the returned `cursor` in the next call. Never parse or cache the cursor — it is opaque and may change encoding.

```typescript
// workers/list-all-keys.ts
export async function listAllKeys(
  namespace: KVNamespace,
  prefix?: string
): Promise<KVNamespaceListKey<unknown>[]> {
  const allKeys: KVNamespaceListKey<unknown>[] = [];
  let cursor: string | undefined;

  do {
    const result = await namespace.list({
      prefix,
      limit: 1000,          // maximum per page
      cursor,
    });

    allKeys.push(...result.keys);
    cursor = result.list_complete ? undefined : result.cursor;
  } while (cursor !== undefined);

  return allKeys;
}

// Usage inside a Worker
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const keys = await listAllKeys(env.MY_NAMESPACE, "user:");
    return Response.json({ total: keys.length });
  },
};
```

### Handling metadata in the listing

`list()` returns the `name`, optional `expiration`, and optional `metadata` for each key. The metadata is whatever you stored at `put()` time — it is returned without an extra round-trip.

```typescript
interface UserMeta {
  createdAt: number;
  tier: "free" | "pro";
}

// Write with metadata
await env.KV.put(`user:${id}`, JSON.stringify(payload), {
  metadata: { createdAt: Date.now(), tier: "free" } satisfies UserMeta,
  expirationTtl: 60 * 60 * 24 * 90, // 90 days
});

// Read metadata during list — no extra get() needed
const { keys } = await env.KV.list<UserMeta>({ prefix: "user:" });
for (const key of keys) {
  if (key.metadata?.tier === "pro") {
    console.log(key.name, key.expiration);
  }
}
```

---

## Bulk Write via Wrangler CLI

The Wrangler CLI wraps the REST API bulk-write endpoint. You prepare a JSON array of objects, each with `key`, `value`, optional `expiration_ttl`, and optional `metadata`.

```bash
# Generate the bulk payload
node -e "
const rows = Array.from({ length: 5000 }, (_, i) => ({
  key: \`item:\${i}\`,
  value: JSON.stringify({ index: i }),
  expiration_ttl: 86400,
  metadata: { batch: 'seed-2026-08' },
}));
require('fs').writeFileSync('bulk.json', JSON.stringify(rows));
"

# Upload — Wrangler splits automatically if > 10 000 entries
npx wrangler kv key put-bulk \
  --namespace-id=<YOUR_NS_ID> \
  bulk.json
```

The `put-bulk` sub-command (`wrangler kv key put-bulk`) was added in Wrangler v3. For older scripts that still call the REST API directly, use:

```bash
curl -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces/${KV_NS_ID}/bulk" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d @bulk.json
```

---

## Bulk Delete via REST API

There is no `wrangler kv key delete-bulk` command yet (as of 2025). Use the REST endpoint directly:

```typescript
// scripts/bulk-delete.ts  (runs with: npx tsx scripts/bulk-delete.ts)
const CF_ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const CF_API_TOKEN = process.env.CF_API_TOKEN!;
const KV_NS_ID = process.env.KV_NS_ID!;

async function bulkDelete(keys: string[]): Promise<void> {
  // Chunk into batches of 10 000
  for (let i = 0; i < keys.length; i += 10_000) {
    const batch = keys.slice(i, i + 10_000);
    const res = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces/${KV_NS_ID}/bulk/delete`,
      {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${CF_API_TOKEN}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(batch),
      }
    );
    if (!res.ok) {
      const err = await res.json();
      throw new Error(`Bulk delete failed: ${JSON.stringify(err)}`);
    }
    console.log(`Deleted batch ${i / 10_000 + 1} (${batch.length} keys)`);
  }
}

// Enumerate all keys then delete
const NAMESPACE_URL = `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces/${KV_NS_ID}/keys`;

async function listAllViaAPI(): Promise<string[]> {
  const keys: string[] = [];
  let cursor: string | undefined;

  do {
    const url = new URL(NAMESPACE_URL);
    url.searchParams.set("limit", "1000");
    if (cursor) url.searchParams.set("cursor", cursor);

    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${CF_API_TOKEN}` },
    });
    const data = (await res.json()) as {
      result: { name: string }[];
      result_info: { cursor?: string };
    };

    keys.push(...data.result.map((k) => k.name));
    cursor = data.result_info.cursor;
  } while (cursor);

  return keys;
}

const all = await listAllViaAPI();
console.log(`Found ${all.length} keys. Deleting…`);
await bulkDelete(all);
```

---

## Streaming Pagination with Rate-Back-Pressure

Large namespaces (millions of keys) can generate so many `list()` calls that you exhaust the per-minute API rate limit. Add a simple back-pressure delay:

```typescript
async function* streamKeys(
  namespace: KVNamespace,
  options: { prefix?: string; delayMs?: number } = {}
): AsyncGenerator<KVNamespaceListKey<unknown>> {
  let cursor: string | undefined;
  const delay = options.delayMs ?? 0;

  do {
    const page = await namespace.list({ prefix: options.prefix, limit: 1000, cursor });
    for (const key of page.keys) yield key;

    cursor = page.list_complete ? undefined : page.cursor;
    if (cursor && delay > 0) {
      await new Promise((r) => setTimeout(r, delay));
    }
  } while (cursor !== undefined);
}

// Consumer
for await (const key of streamKeys(env.KV, { prefix: "session:", delayMs: 50 })) {
  if ((key.expiration ?? Infinity) < Date.now() / 1000) {
    await env.KV.delete(key.name);
  }
}
```

---

## Anti-patterns

- **Storing the cursor between requests.** Cursors are short-lived and tied to namespace state. If you store a cursor in KV itself and the namespace is modified between calls, the cursor may skip or repeat keys. Complete the full scan in a single execution context (or a Durable Object alarm chain).
- **Using `list()` as a secondary index.** KV is not a database. If you need to query by metadata value (e.g., "all users on the pro tier"), maintain a separate index in D1 or another KV key that holds a JSON array of matching keys.
- **Assuming list order.** Keys are returned in lexicographic order by name. This is implementation detail, not a contract — do not depend on it for correctness.
- **Bulk-writing to prod from localhost without `--env`.** `wrangler kv key put-bulk` defaults to the `preview` namespace unless you pass `--env production` or use `--namespace-id` explicitly. Double-check the namespace ID before running.

---

## Gotchas

1. **`list_complete: true` does not mean zero cursor.** Some Cloudflare SDK versions return a cursor even when `list_complete` is `true`. The correct check is `!result.list_complete` before reading `result.cursor`.
2. **Deleted keys appear in list during eventual consistency window.** KV is eventually consistent globally. A key you just deleted in region A may still appear in `list()` results served from region B for up to 60 seconds.
3. **Metadata counts toward the 1 KiB per-key metadata limit, not the 25 MiB value limit.** Storing large JSON in metadata will silently truncate or reject the write.
4. **`put-bulk` does not validate JSON values.** If your value is a binary blob encoded as base64, you must set `"base64": true` per entry; otherwise KV stores the raw base64 string, not the decoded bytes.
5. **Workers runtime has no batch `get`.** You must issue individual `get()` calls or use `Promise.all()`. There is no multi-key fetch in the Worker binding; that exists only in the REST API via the `keys` query parameter approach (undocumented, subject to change).

---

## Verification

```bash
# Confirm namespace ID and key count
npx wrangler kv namespace list

# Spot-check first page of a prefix
npx wrangler kv key list --namespace-id=<NS_ID> --prefix="user:" --limit=10

# Verify a specific key and its metadata
npx wrangler kv key get --namespace-id=<NS_ID> "user:abc123"
```

In a Worker integration test (using `@cloudflare/vitest-pool-workers`):

```typescript
import { env } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { listAllKeys } from "../workers/list-all-keys";

describe("listAllKeys", () => {
  beforeEach(async () => {
    await env.MY_NAMESPACE.put("a:1", "one");
    await env.MY_NAMESPACE.put("a:2", "two");
    await env.MY_NAMESPACE.put("b:1", "three");
  });

  it("returns all keys with prefix", async () => {
    const keys = await listAllKeys(env.MY_NAMESPACE, "a:");
    expect(keys.map((k) => k.name)).toEqual(["a:1", "a:2"]);
  });
});
```

---

## Related

- `kv-best-practices.md` — general KV design patterns and TTL strategy
- `kv-eventually-consistent.md` — understanding the consistency model
- `kv-namespace-migration.md` — migrating data between namespaces
- `d1-best-practices.md` — when to graduate from KV to a relational store
- `workers-vitest-pool-integration-testing.md` — testing Workers bindings locally

---

## Sources

- Cloudflare Workers KV API reference: https://developers.cloudflare.com/kv/api/
- KV REST API (bulk operations): https://developers.cloudflare.com/api/operations/workers-kv-namespace-bulk-write-key-value-pairs
- Wrangler KV commands: https://developers.cloudflare.com/workers/wrangler/commands/#kv-key
