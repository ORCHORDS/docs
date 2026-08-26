# Cloudflare API Pagination Automation with Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your Worker or CI script iterates the Cloudflare REST API — listing DNS records, Worker
scripts, KV keys, D1 databases, or zone rulesets — and silently returns only the first
50 results because you forgot to handle pagination. At scale (hundreds of zones, thousands
of KV keys), incomplete data causes silent bugs in automation pipelines.

---

## Context

Cloudflare uses two pagination schemes depending on the endpoint:

1. **Page-based** (`page` + `per_page` + `result_info.total_pages`) — used by most
   account/zone list endpoints (zones, DNS records, members, rules).
2. **Cursor-based** (`cursor` token in `result_info.cursor`) — used by KV key listing
   and some newer endpoints. Never has a `total_pages` field.

Both schemes return a `result_info` envelope. Default `per_page` is 20; max is 1000 on
most endpoints (50 on some). Always set `per_page=100` to reduce round trips.

All code below runs in a Cloudflare Worker or Node.js CI with the same `fetch()` API.

---

## 1. Generic Page-Based Paginator

```typescript
// src/lib/cf-paginate.ts

const CF_BASE = "https://api.cloudflare.com/client/v4";

interface CfResultInfo {
  page:        number;
  per_page:    number;
  count:       number;
  total_count: number;
  total_pages: number;
  cursor?:     string;
}

interface CfListResponse<T> {
  result:      T[];
  result_info: CfResultInfo;
  success:     boolean;
  errors:      { code: number; message: string }[];
}

/**
 * Collect all pages from a page-based CF list endpoint.
 * Passes `page` and `per_page` as query params.
 */
export async function paginateAll<T>(
  path: string,
  token: string,
  params: Record<string, string> = {},
  perPage = 100,
): Promise<T[]> {
  const results: T[] = [];
  let page = 1;

  while (true) {
    const url = new URL(`${CF_BASE}${path}`);
    url.searchParams.set("page",     String(page));
    url.searchParams.set("per_page", String(perPage));
    for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);

    const res = await fetch(url.toString(), {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (!res.ok) throw new Error(`CF API error ${res.status} on ${path} page ${page}`);

    const data = await res.json<CfListResponse<T>>();
    if (!data.success) {
      throw new Error(`CF API failed: ${data.errors.map((e) => e.message).join(", ")}`);
    }

    results.push(...data.result);

    if (page >= data.result_info.total_pages || data.result.length === 0) break;
    page++;
  }

  return results;
}
```

---

## 2. Cursor-Based Paginator (KV Keys, Newer Endpoints)

```typescript
/**
 * Collect all pages from a cursor-based CF list endpoint.
 * Passes `cursor` as a query param; stops when `result_info.cursor` is absent.
 */
export async function cursorPaginateAll<T>(
  path: string,
  token: string,
  params: Record<string, string> = {},
  limit = 1000,
): Promise<T[]> {
  const results: T[] = [];
  let cursor: string | undefined;

  while (true) {
    const url = new URL(`${CF_BASE}${path}`);
    url.searchParams.set("limit", String(limit));
    for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
    if (cursor) url.searchParams.set("cursor", cursor);

    const res = await fetch(url.toString(), {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (!res.ok) throw new Error(`CF API cursor error ${res.status} on ${path}`);

    const data = await res.json<CfListResponse<T>>();
    if (!data.success) {
      throw new Error(`CF API failed: ${data.errors.map((e) => e.message).join(", ")}`);
    }

    results.push(...data.result);

    cursor = data.result_info.cursor;
    if (!cursor || data.result.length === 0) break;
  }

  return results;
}
```

---

## 3. Rate-Limit-Aware Batch Fetcher

```typescript
/**
 * Fetch pages with exponential backoff on 429 / 5xx.
 */
async function fetchWithRetry(
  url: string,
  token: string,
  maxRetries = 5,
): Promise<Response> {
  let delay = 500; // ms

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (res.status === 429) {
      const retryAfter = Number(res.headers.get("Retry-After") ?? "1");
      await sleep(Math.max(retryAfter * 1000, delay));
      delay *= 2;
      continue;
    }
    if (res.status >= 500) {
      await sleep(delay);
      delay = Math.min(delay * 2, 30_000);
      continue;
    }
    return res;
  }
  throw new Error(`Max retries exceeded fetching ${url}`);
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
```

---

## 4. Practical Usage: List All DNS Records Across All Zones

```typescript
// src/lib/dns-inventory.ts

interface DnsRecord {
  id:      string;
  name:    string;
  type:    string;
  content: string;
  zone_id: string;
}

interface Zone {
  id:   string;
  name: string;
}

export async function getAllDnsRecords(
  accountId: string,
  token: string,
): Promise<DnsRecord[]> {
  // 1. Collect all zones for the account
  const zones = await paginateAll<Zone>(
    `/accounts/${accountId}/zones`,
    token,
  );

  // 2. For each zone, collect all DNS records (run concurrently, capped at 5)
  const allRecords: DnsRecord[] = [];
  const CONCURRENCY = 5;

  for (let i = 0; i < zones.length; i += CONCURRENCY) {
    const batch = zones.slice(i, i + CONCURRENCY);
    const results = await Promise.all(
      batch.map((zone) =>
        paginateAll<DnsRecord>(`/zones/${zone.id}/dns_records`, token)
          .then((records) => records.map((r) => ({ ...r, zone_id: zone.id }))),
      ),
    );
    allRecords.push(...results.flat());
  }

  return allRecords;
}
```

---

## 5. Cursor Pagination: List All KV Keys in a Namespace

```typescript
interface KvKey {
  name:       string;
  expiration?: number;
  metadata?:  unknown;
}

export async function listAllKvKeys(
  accountId: string,
  namespaceId: string,
  token: string,
  prefix?: string,
): Promise<KvKey[]> {
  return cursorPaginateAll<KvKey>(
    `/accounts/${accountId}/storage/kv/namespaces/${namespaceId}/keys`,
    token,
    prefix ? { prefix } : {},
    1000,
  );
}
```

---

## 6. Worker Handler — On-Demand Inventory Endpoint

```typescript
// src/index.ts
interface Env {
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN:  string;  // Worker secret
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    if (url.pathname === "/inventory/dns") {
      const records = await getAllDnsRecords(env.CF_ACCOUNT_ID, env.CF_API_TOKEN);
      return Response.json({ count: records.length, records });
    }

    if (url.pathname === "/inventory/zones") {
      const zones = await paginateAll<Zone>(
        `/accounts/${env.CF_ACCOUNT_ID}/zones`,
        env.CF_API_TOKEN,
      );
      return Response.json({ count: zones.length, zones });
    }

    return new Response("Not Found", { status: 404 });
  },
};
```

---

## Anti-patterns

- **Assuming `result.length < per_page` means last page** — some endpoints return a
  partial last page but `total_pages` is the authoritative signal. Use `result_info`.
- **Fetching all pages sequentially when order does not matter** — parallelise across
  independent resources (zones, namespaces) for 5–10× throughput.
- **Ignoring `result_info.cursor` when it's present** — if a `cursor` exists alongside
  `total_pages`, the endpoint is in cursor mode; ignore `total_pages` and follow the
  cursor.
- **No backoff on 429** — Cloudflare rate limits vary by endpoint (1 200 req/5 min for
  most account APIs). Always implement `Retry-After`-aware backoff.
- **Logging full paginated responses in production** — can flood Logpush with MB of JSON
  per invocation. Log counts and error states only.

---

## Gotchas

- The `per_page` maximum varies: DNS records allow 1 000; account members allow 50;
  Workers scripts allow 100. Check the API reference per endpoint.
- KV key listing does **not** support `per_page`; it uses `limit` (max 1 000) with
  cursor. The response's `result_info` contains only `count`, not `total_count`.
- `result_info.total_count` is sometimes 0 even on non-empty results for cursor-based
  endpoints — do not use it to break the loop.
- Zones list via `/zones` is scoped to the **token's** account unless you pass
  `?account.id=...`; always pass `account_id` to avoid cross-account leakage.
- Some endpoints (Rulesets, Firewall Rules) use their own pagination or return all items
  in one call — check before adding a paginator.

---

## Verification

```bash
# Manually check page 1 and confirm result_info
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/zones?per_page=5&page=1" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result_info'

# Expect:
# { "page": 1, "per_page": 5, "count": 5, "total_count": 42, "total_pages": 9 }

# KV cursor pagination — first page
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/storage/kv/namespaces/$NS_ID/keys?limit=5" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result_info'
# Expect: { "count": 5, "cursor": "some-opaque-string" }
```

---

## Related

- `cloudflare-account-member-role-automation-workers.md`
- `cloudflare-workers-api-token-scoping.md`
- `cloudflare-workers-kv-namespace-terraform.md`
- `cloudflare-dns-api.md`

---

## Sources

- CF API pagination: https://developers.cloudflare.com/fundamentals/api/reference/pagination/
- CF rate limits: https://developers.cloudflare.com/fundamentals/api/reference/limits/
- KV key list API: https://developers.cloudflare.com/api/operations/workers-kv-namespace-list-a-namespace-'s-keys
- Zones list API: https://developers.cloudflare.com/api/operations/zones-get
