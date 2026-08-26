# Locale-Aware Sorting with Intl.Collator in Workers When SQLite ICU Is Unavailable

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You query a D1 database and need results sorted by a text column in locale-correct order—Swedish `å ä ö` after `z`, German `ß` near `ss`, Turkish `İ` distinct from `I`. D1 runs SQLite without the optional ICU extension, so `ORDER BY name COLLATE NOCASE` uses binary ordering and produces incorrect results for non-ASCII text.

## Context

- Cloudflare Workers + D1 (SQLite without ICU)
- Lists of ≤ 5 000 rows where full in-process sort is acceptable
- `Intl.Collator` available in V8 runtime — no npm dependency
- KV used to cache sorted pages (TTL 60 s) to avoid re-sorting on every request

---

## Section 1: Fetching and Sorting in the Application Layer

Query D1 without an `ORDER BY` (or with a coarse primary-key order for stable pagination), then sort in Workers using `Intl.Collator`.

```typescript
// src/lib/locale-sort.ts

export interface Row {
  id: string;
  name: string;

}

/**
 * Sort an array of rows by `name` using locale-aware collation.
 * @param rows   Array of DB rows
 * @param locale BCP-47 locale tag, e.g. 'sv', 'de', 'tr'
 * @param sensitivity 'base' ignores accents+case; 'accent' ignores only case
 */
export function localeSortRows(
  rows: Row[],
  locale: string,
  sensitivity: Intl.CollatorOptions['sensitivity'] = 'variant',
): Row[] {
  const collator = new Intl.Collator(locale, {
    usage: 'sort',
    sensitivity,
    numeric: true,   // "item2" before "item10"
    caseFirst: 'upper',
  });
  return [...rows].sort((a, b) => collator.compare(a.name, b.name));
}
```

---

## Section 2: D1 Query + Sort + KV Page Cache

```typescript
// src/handlers/list-items.ts
import type { Env } from '../types';
import { localeSortRows, type Row } from '../lib/locale-sort';

const PAGE_SIZE = 50;
const KV_TTL_SECONDS = 60;

function cacheKey(locale: string, page: number): string {
  return `sorted-list:${locale}:page:${page}`;
}

export async function handleListItems(
  request: Request,
  env: Env,
): Promise<Response> {
  const url = new URL(request.url);
  const locale = url.searchParams.get('locale') ?? 'en';
  const page   = Math.max(1, parseInt(url.searchParams.get('page') ?? '1', 10));

  // 1. Try KV cache
  const key = cacheKey(locale, page);
  const cached = await env.KV.get(key, 'json');
  if (cached !== null) {
    return Response.json({ data: cached, source: 'cache' });
  }

  // 2. Fetch ALL rows from D1 (acceptable for ≤5 000 rows)
  //    For larger datasets, fetch only the relevant page after a coarse sort.
  const { results } = await env.DB
    .prepare('SELECT id, name FROM items')
    .all<Row>();

  // 3. Sort in application layer
  const sorted = localeSortRows(results, locale);

  // 4. Paginate
  const start = (page - 1) * PAGE_SIZE;
  const pageRows = sorted.slice(start, start + PAGE_SIZE);

  // 5. Write page to KV with TTL
  await env.KV.put(key, JSON.stringify(pageRows), {
    expirationTtl: KV_TTL_SECONDS,
  });

  return Response.json({ data: pageRows, source: 'db' });
}
```

---

## Section 3: Invalidating KV Cache on Write

When an item is created, updated, or deleted, all cached pages for every locale must be invalidated. Use a KV list-and-delete pattern.

```typescript
// src/lib/cache-invalidate.ts
import type { KVNamespace } from '@cloudflare/workers-types';

const SUPPORTED_LOCALES = ['en', 'de', 'sv', 'tr', 'fr', 'ja'];

export async function invalidateSortedCache(kv: KVNamespace): Promise<void> {
  // Build all possible keys — faster than KV list() for known key patterns
  // KV list is eventually consistent; explicit deletes are stronger
  const deletes: Promise<void>[] = [];

  for (const locale of SUPPORTED_LOCALES) {
    // Delete pages 1-20 eagerly; beyond that rely on TTL expiry
    for (let p = 1; p <= 20; p++) {
      deletes.push(kv.delete(`sorted-list:${locale}:page:${p}`));
    }
  }

  await Promise.all(deletes);
}

// Usage in a mutation handler:
// await env.DB.prepare('INSERT INTO items VALUES (?1, ?2)').bind(id, name).run();
// await invalidateSortedCache(env.KV);
```

For very large locale × page matrices, switch to KV list with prefix:

```typescript
export async function invalidateByPrefix(
  kv: KVNamespace,
  prefix: string,
): Promise<void> {
  let cursor: string | undefined;
  do {
    const list = await kv.list({ prefix, cursor, limit: 1000 });
    await Promise.all(list.keys.map((k) => kv.delete(k.name)));
    cursor = list.list_complete ? undefined : list.cursor;
  } while (cursor);
}
// Call: await invalidateByPrefix(env.KV, 'sorted-list:');
```

---

## Anti-patterns

- **`ORDER BY name COLLATE NOCASE`** — binary collation, wrong for accented characters.
- **Sorting on the client** — doubles payload size and wastes bandwidth.
- **Creating a new `Intl.Collator` inside `.sort()`** — called O(n log n) times; always instantiate once outside the comparator.
- **Caching the entire sorted array** — KV values max out at 25 MB; cache paginated slices.
- **Assuming locale from `Accept-Language` without normalisation** — normalise BCP-47 tags (`zh-Hant-TW` → keep as-is; `EN_US` → `en-US`) before using as a cache key.

## Gotchas

- `Intl.Collator` with `sensitivity: 'base'` treats `a`, `á`, and `A` as equal — use `'variant'` if you need accent-sensitive uniqueness.
- KV `list()` is eventually consistent; a key deleted milliseconds ago may still appear in a list. Explicit `delete()` calls are consistent for subsequent `get()` operations.
- Sorting 5 000 rows in Workers takes < 10 ms; at 50 000 rows consider a dedicated sort worker invoked async.
- `numeric: true` in Collator options handles `item2 < item10` correctly but treats leading zeros specially (`01` < `1` in some locales).

---

## Verification

```bash
# Create local D1 and seed Swedish names
npx wrangler d1 execute my-db --local --command \
  "CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY, name TEXT NOT NULL)"

npx wrangler d1 execute my-db --local --command "
  INSERT INTO items VALUES
    ('1','Åsa'),('2','Zebra'),('3','Örjan'),('4','Abel'),('5','Äta');
"

# Start dev server
npx wrangler dev

# Request sorted page with Swedish locale
curl 'http://localhost:8787/items?locale=sv&page=1' | jq '.data[].name'
# Expected order: Abel, Zebra, Åsa, Äta, Örjan

# Second request should come from KV cache
curl 'http://localhost:8787/items?locale=sv&page=1' | jq '.source'
# Expected: "cache"
```

---

## Related

- `documentation/docs/policies/i18n/workers-timezone-aware-scheduling-intl.md`
- `documentation/docs/policies/i18n/workers-locale-aware-url-slug-generation.md`
- `documentation/docs/policies/i18n/workers-intl-displaynames-locale-labels.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/kv/
- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Collator
- https://www.sqlite.org/lang_corefunc.html (no ICU in D1)
