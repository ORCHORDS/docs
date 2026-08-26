# cost-optimization-cloudflare

**Issue:** Cloudflare costs — Workers, D1, R2, KV, Queues, Vectorize
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your CF bill is $5k/month. You have 10M requests/day. Most
requests are served by the static asset cache. The Workers
bill is high. The D1 bill is high. You don't know where the
money is going.

## Root cause
**CF costs are usage-based.** Each request, each D1 read, each
KV get, each R2 operation has a cost. At scale, small
inefficiencies add up.

**Source:** CF pricing:
https://developers.cloudflare.com/workers/platform/pricing/

## The cost breakdown

### Pages
- **Requests:** Free (unlimited)
- **Bandwidth:** Free (unlimited)
- **Functions (Workers):** Charged as Workers

### Workers
- **Requests:** $0.30 per million (Bundled) / $0.50 per
  million (Unbound)
- **CPU time:** $0.02 per million ms (Bundled) / $0.0125 per
  million ms (Unbound)
- **Duration:** First 30s free, $0.000018 per GB-second after

### D1
- **Rows read:** $0.001 per million
- **Rows written:** $1.00 per million
- **Storage:** $0.75 per GB-month
- **Note:** Reads are 1000x cheaper than writes

### R2
- **Storage:** $0.015 per GB-month
- **Class A operations (PUT, POST, LIST):** $4.50 per million
- **Class B operations (GET, HEAD):** $0.36 per million
- **Egress:** Free

### KV
- **Reads:** $0.50 per million
- **Writes:** $5.00 per million
- **Storage:** $0.50 per GB-month
- **Note:** Reads are 10x cheaper than writes

### Queues
- **Operations:** $0.40 per million
- **Storage:** Free for first 1 GB, then $0.20 per GB-month

### Vectorize
- **Storage:** $0.05 per 1000 vectors per month
- **Queries:** $0.01 per 1000 dimensions queried

## The optimization patterns

### 1. Cache aggressively
The cheapest request is one that doesn't happen.
```ts
// Read from KV (cheap)
// On miss, read from D1 (expensive)
// On miss, store in KV (write cost)
// Future requests: read from KV (cheap)
```

A 90% cache hit rate = 10x reduction in D1 reads.

### 2. Use the right store for the right access pattern

| Access pattern | Use |
|---|---|
| Hot config, < 10ms reads | KV |
| Bulk relational data | D1 |
| Object storage (files) | R2 |
| Session / rate limit state | DO |
| Semantic search | Vectorize |
| Async work | Queues |

### 3. Batch D1 operations
D1 reads are 1000x cheaper than writes. So:
- **Batch reads:** one query for many rows
- **Avoid N+1 queries**
- **Cache results in KV**

### 4. Compress payloads
Workers CPU time includes the cost of serialization. Smaller
payloads = less CPU = less cost.

```ts
const json = JSON.stringify(data);
const compressed = new CompressionStream('gzip').write(json);
```

### 5. Use static assets where possible
A static asset (HTML, CSS, JS) is served from the edge cache
for free. A Worker call costs money. For the homepage,
product pages, etc., static is cheaper.

### 6. Right-size Workers
The Bundled plan ($5/mo) is cheaper than Unbound ($5/mo + usage).
But Unbound has higher limits. Right-size:
- **Low traffic:** Bundled
- **High traffic:** Unbound (the per-request cost is lower)

### 7. Monitor + alert
Set up billing alerts:
- "Daily spend > $100" → page on-call
- "Daily spend > 2x the 7-day average" → page on-call

CF has built-in spend notifications. Configure them.

## The cost-monitoring dashboard

Track daily:
- Workers: requests, CPU, memory
- D1: rows read, rows written, storage
- R2: storage, class A, class B
- KV: reads, writes, storage
- Queues: operations
- Vectorize: storage, queries

The dashboard should be visible to the team. The on-call
should check it weekly.

## The "cost review" routine

Monthly:
1. Review the bill (top 3 cost drivers)
2. Identify 1 optimization (cache, batch, etc.)
3. Implement + measure
4. Document in the KB (e.g. this entry)

The "small wins" add up: 5 optimizations × 10% savings = 50%
total reduction.

## Verification
- **Live:** CF billing dashboard + custom Grafana dashboard
- **Audit:** Monthly cost review meeting
- **Process:** Quarterly architecture review for cost

## Gotchas
- **CF Workers has a free tier** (100k req/day). For dev, this
  is plenty. For prod, expect to pay.
- **The "unlimited" plan for Pages** is actually unlimited
  for static assets, but Workers + D1 are still metered.
- **D1's "rows read" is the number of rows scanned**, not
  rows returned. A query with `WHERE` that returns 1 row may
  scan 1M rows. Use indexes.
- **R2 class A operations are expensive** ($4.50/M). For high-
  write workloads (e.g. user uploads), consider a separate
  store or a queue + batch.
- **Vectorize costs add up at scale.** 10M vectors × $0.05/1k
  = $500/month just for storage. Consider pruning old
  vectors.
- **The "Bundled" plan has a 30s CPU cap** (per request).
  Long-running work must use a queue + worker.

## Related
- `cache-strategies.md`
- `scaling-cf-workers.md`
- `kv-eventually-consistent.md`
- CF pricing: https://developers.cloudflare.com/workers/platform/pricing/
- CF D1 pricing: https://developers.cloudflare.com/d1/platform/pricing/
- CF R2 pricing: https://developers.cloudflare.com/r2/pricing/
