# feature-cookbook-cost-optimization

**Issue:** Cost optimization — CF Workers, D1, R2, AI
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your CF bill is $10k/month. You look at the usage. 80%
of the Workers' CPU time is spent on a single endpoint.
The endpoint is "list all users." You don't need to
return all users. You could paginate.

## Root cause
**Cloud costs grow with usage.** Without optimization,
the bill grows with traffic.

**Source:** CF pricing docs.

## CF Workers pricing

- **Free:** 100k requests/day
- **Paid ($5/mo):** 10M requests/mo, 30M CPU ms
- **Bundled:** $0.50/M requests, $0.02/M CPU ms

A 1M request/day app at $5/mo + usage = $20-50/mo.

## D1 pricing

- **Read:** $0.001/M rows
- **Write:** $1.00/M rows
- **Storage:** $0.75/GB/mo

A 10GB DB with 1M reads/day and 100k writes/day = $5-15/mo.

## R2 pricing

- **Storage:** $0.015/GB/mo
- **Class A (write):** $4.50/M
- **Class B (read):** $0.36/M
- **Egress:** Free

A 1TB bucket with 10M reads = $15 + $3.6 = $18.6/mo.

## The "Workers cost" pattern

For Workers, minimize CPU time:
- **Cache:** Cache at the edge (Cache API)
- **Stream:** Stream large responses
- **Optimize:** Avoid expensive operations
- **Truncate:** Return only what's needed

```ts
// ❌ Returns all users
const users = await env.DB!.prepare(`SELECT * FROM users`).all();
return Response.json(users.results);

// ✅ Paginates + selects only what's needed
const { results } = await env.DB!.prepare(
  `SELECT id, display_name, email FROM users LIMIT ? OFFSET ?`
).bind(20, offset).all();
return Response.json(results);
```

Less CPU + less data transfer.

## The "D1 cost" pattern

For D1, minimize reads + writes:
- **Index:** Index the queried columns
- **Select:** Only the columns you need
- **Cache:** Cache frequent reads
- **Batch:** Batch multiple writes

```ts
// ❌ Returns all columns
const user = await env.DB!.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first();

// ✅ Returns only the columns
const user = await env.DB!.prepare(`SELECT id, display_name FROM users WHERE id = ?`).bind(id).first();
```

D1 charges per row read + per row scanned.

## The "R2 cost" pattern

For R2, optimize:
- **Compress:** gzip / brotli
- **CDN:** Cache via CF
- **Lifecycle:** Move cold data to infrequent access
- **Egress:** Free, but check origin requests

```ts
// Cache R2 reads
const cached = await caches.default.match(request);
if (cached) return cached;

const obj = await env.R2!.get(key);
const response = new Response(obj!.body, {
  headers: { 'cache-control': 'public, max-age=86400' },
});
await caches.default.put(request, response.clone());
return response;
```

R2 reads are cheap; CF cache is free.

## The "AI cost" pattern

For AI, use the right model:
- **LLaMA 2 7B:** Fast, cheap
- **LLaMA 2 13B:** Slower, more accurate
- **Mistral 7B:** Fast, good
- **OpenAI GPT-4o:** Most expensive, most accurate

For most apps, **LLaMA 2 7B** is enough.

```ts
// Use the smallest model
const response = await env.AI.run('@cf/meta/llama-2-7b-chat-int8', { prompt });
```

Smaller models are 10-100x cheaper.

## The "cache" pattern

For caching, use Cache API:
```ts
async function getCachedOrFetch<T>(key: string, ttl: number, fetcher: () => Promise<T>): Promise<T> {
  const cache = await caches.open('api');
  const cached = await cache.match(key);
  if (cached) return cached.json();

  const fresh = await fetcher();
  const response = new Response(JSON.stringify(fresh), {
    headers: { 'cache-control': `max-age=${ttl}` },
  });
  await cache.put(key, response);
  return fresh;
}
```

The cache is free + reduces upstream cost.

## The "queue batching" pattern

For queue batching:
```ts
// ❌ One message per row
for (const user of users) {
  await env.QUEUE.send({ type: 'process_user', userId: user.id });
}

// ✅ One message per batch
for (let i = 0; i < users.length; i += 100) {
  await env.QUEUE.send({ type: 'process_chunk', users: users.slice(i, i + 100) });
}
```

Less queue operations.

## The "observability" pattern

For cost observability:
- **Per-endpoint cost:** Tag each request with the
  endpoint + tenant
- **Cost alerts:** Alert when a tenant's cost > $X
- **Cost dashboard:** Show top spenders

```ts
// Tag the cost
const tags = { endpoint: 'POST /api/users', tenantId: user.tenantId };
logEvent('cost.usage', 'info', { durationMs, dbRows: rowCount, ...tags });
```

The cost is observable per request.

## The "lifecycle" pattern

For data lifecycle, archive cold data:
- **Hot:** Accessed daily → D1
- **Warm:** Accessed monthly → R2 (standard)
- **Cold:** Accessed yearly → R2 (Infrequent Access)
- **Archive:** > 1 year → R2 (Archive)

The cost drops as data ages.

## The "feature cost" pattern

For each feature, calculate the cost:
- **AI inference:** $X / 1000 calls
- **DB read:** $Y / 1000 calls
- **DB write:** $Z / 1000 calls
- **Storage:** $A / GB / mo

A feature that costs $1 to run is OK if it makes $5.

## The "tenant cost" pattern

For multi-tenant, charge per usage:
- **Free tier:** 1k requests/mo
- **Paid tier:** $X per 10k requests
- **Pro tier:** $Y per 100k requests

The customer pays for what they use.

## The "cost anti-pattern" anti-patterns

### 1. No pagination
- **Issue:** A 10k-row response is expensive
- **Fix:** Paginate

### 2. No caching
- **Issue:** Every request hits the DB
- **Fix:** Cache at the edge

### 3. SELECT *
- **Issue:** A 50-column row transfer is wasteful
- **Fix:** Select only what's needed

### 4. AI overkill
- **Issue:** GPT-4 for a "summarize this" task
- **Fix:** LLaMA 2 7B

### 5. Hot data in archive storage
- **Issue:** 1M reads/mo from R2 Archive = $360
- **Fix:** Move to standard

### 6. No observability
- **Issue:** You don't know what's expensive
- **Fix:** Cost dashboard

## Verification
- **Test:** Each feature's cost is calculated
- **Test:** Caching is working
- **Live:** Cost dashboard is reviewed
- **Audit:** Quarterly cost review

## Gotchas
- **The "no pagination" anti-pattern.** Big responses are
  expensive.
- **The "no caching" anti-pattern.** Every request hits
  the DB.
- **The "AI overkill" anti-pattern.** Use the smallest
  model.
- **The "no observability" anti-pattern.** You can't
  optimize what you don't measure.

## Related
- `cost-optimization-cloudflare.md`
- `scaling-cf-workers.md`
- `caching-strategies-detail.md`
- `feature-cookbook-analytics.md`
- `feature-cookbook-monitoring.md`
- CF pricing: https://developers.cloudflare.com/workers/platform/pricing/
- D1 pricing: https://developers.cloudflare.com/d1/platform/pricing/
- R2 pricing: https://developers.cloudflare.com/r2/pricing/
