# k6 Workers Vectorize Semantic Search Load Test
- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
You have a Cloudflare Worker that accepts a search query, embeds it via Workers AI, queries a
Vectorize index for nearest neighbours, and returns ranked results. You need to validate that:
1. P99 latency stays under your SLO (e.g. 800 ms) under concurrent user load.
2. Vectorize query accuracy (result count, score floor) does not degrade at load.
3. Workers AI embedding calls do not become a bottleneck at moderate concurrency.
4. The Worker handles embedding or Vectorize errors gracefully (no 500 cascades).

## Context
Vectorize queries are proxied through Cloudflare's global network; latency varies by vector
dimension count, top-K, and whether the AI binding is in the same PoP. k6's `http` module, custom
`Trend` metrics, and threshold gates are the right tool to validate the latency envelope. Query
payloads should be drawn from a realistic fixture corpus to avoid cache skew.

## Worker Under Test
`src/search.ts`:
```typescript
export interface Env {
  AI: Ai;
  SEARCH_INDEX: VectorizeIndex;
}

export interface SearchResult {
  id: string;
  score: number;
  metadata: Record<string, string> | null;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== 'POST' || new URL(req.url).pathname !== '/search') {
      return new Response('Not found', { status: 404 });
    }

    let body: { query: string; topK?: number };
    try {
      body = await req.json<{ query: string; topK?: number }>();
    } catch {
      return new Response('Bad request', { status: 400 });
    }

    const { query, topK = 5 } = body;
    if (!query || typeof query !== 'string') {
      return new Response('Missing query', { status: 400 });
    }

    // Embed the query
    const embedResponse = await env.AI.run('@cf/baai/bge-small-en-v1.5', { text: [query] });
    const vector = (embedResponse as { data: number[][] }).data[0];

    // Query Vectorize
    const matches = await env.SEARCH_INDEX.query(vector, {
      topK,
      returnMetadata: 'indexed',
    });

    const results: SearchResult[] = matches.matches.map((m) => ({
      id: m.id,
      score: m.score,
      metadata: m.metadata ? (m.metadata as Record<string, string>) : null,
    }));

    return Response.json({ results, count: results.length });
  },
};
```

## Query Fixture Corpus
`k6/fixtures/search-queries.json`:
```json
[
  { "query": "machine learning model deployment" },
  { "query": "cloudflare workers performance optimization" },
  { "query": "vector similarity search algorithms" },
  { "query": "real-time data streaming pipeline" },
  { "query": "edge computing latency reduction" },
  { "query": "semantic embeddings natural language processing" },
  { "query": "API rate limiting best practices" },
  { "query": "distributed key-value store design" },
  { "query": "WebSocket connection management" },
  { "query": "content delivery network caching strategy" }
]
```

## k6 Load Test
`k6/vectorize-search-load-test.js`:
```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Counter, Rate } from 'k6/metrics';
import { SharedArray } from 'k6/data';

// Metrics
const searchLatency = new Trend('search_latency_ms', true);
const embeddingLatency = new Trend('embedding_latency_ms', true);
const resultCount = new Trend('result_count');
const scoreFloor = new Trend('result_min_score');
const errorCount = new Counter('search_errors');
const successRate = new Rate('search_success');

const BASE_URL = __ENV.WORKER_URL ?? 'http://localhost:8787';

// Shared query corpus – loaded once, read-only across VUs
const queries = new SharedArray('queries', function () {
  return JSON.parse(open('./fixtures/search-queries.json'));
});

export const options = {
  scenarios: {
    // Ramp up to 20 concurrent users over 30 s, hold for 2 min, ramp down
    sustained_load: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '30s', target: 20 },
        { duration: '2m',  target: 20 },
        { duration: '15s', target: 0  },
      ],
    },
    // Spike to 50 VUs for 10 s to test burst handling
    spike: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '5s',  target: 50 },
        { duration: '10s', target: 50 },
        { duration: '5s',  target: 0  },
      ],
      startTime: '3m',
    },
  },
  thresholds: {
    // Latency SLO
    'search_latency_ms': ['p(95)<800', 'p(99)<1500'],
    // All responses must be successful
    'search_success': ['rate>0.99'],
    // At least 3 results on average (index health check)
    'result_count': ['avg>=3'],
    // Minimum similarity score floor
    'result_min_score': ['avg>0.5'],
    // Error budget
    'search_errors': ['count<10'],
    // HTTP-level
    'http_req_duration': ['p(95)<900'],
    'http_req_failed': ['rate<0.01'],
  },
};

export default function () {
  // Pick a random query from the corpus
  const fixture = queries[Math.floor(Math.random() * queries.length)];

  const start = Date.now();
  const res = http.post(
    `${BASE_URL}/search`,
    JSON.stringify({ query: fixture.query, topK: 5 }),
    {
      headers: { 'Content-Type': 'application/json' },
      tags: { endpoint: 'vectorize_search' },
    },
  );
  const elapsed = Date.now() - start;
  searchLatency.add(elapsed);

  const ok = check(res, {
    'status is 200': (r) => r.status === 200,
    'body has results': (r) => {
      try {
        const body = JSON.parse(r.body);
        return Array.isArray(body.results);
      } catch {
        return false;
      }
    },
    'result count >= 1': (r) => {
      try {
        return JSON.parse(r.body).count >= 1;
      } catch {
        return false;
      }
    },
  });

  if (ok && res.status === 200) {
    successRate.add(true);
    try {
      const body = JSON.parse(res.body);
      resultCount.add(body.count);

      if (body.results.length > 0) {
        const scores = body.results.map((r) => r.score);
        scoreFloor.add(Math.min(...scores));
      }

      // Check for server-timing header to extract embedding latency
      const timing = res.headers['Server-Timing'];
      if (timing) {
        const match = timing.match(/embed;dur=(\d+)/);
        if (match) embeddingLatency.add(parseInt(match[1]));
      }
    } catch {
      // Non-JSON response already caught by check
    }
  } else {
    successRate.add(false);
    errorCount.add(1);
  }

  sleep(0.5);
}

export function handleSummary(data) {
  return {
    'k6-vectorize-summary.json': JSON.stringify(data, null, 2),
    stdout: `
=== Vectorize Search Load Test Summary ===
p95 latency : ${data.metrics.search_latency_ms?.values?.['p(95)']?.toFixed(0) ?? 'N/A'} ms
p99 latency : ${data.metrics.search_latency_ms?.values?.['p(99)']?.toFixed(0) ?? 'N/A'} ms
avg results : ${data.metrics.result_count?.values?.avg?.toFixed(1) ?? 'N/A'}
min score   : ${data.metrics.result_min_score?.values?.avg?.toFixed(3) ?? 'N/A'}
success rate: ${((data.metrics.search_success?.values?.rate ?? 0) * 100).toFixed(2)} %
errors      : ${data.metrics.search_errors?.values?.count ?? 0}
==========================================
`,
  };
}
```

## CI Workflow
`.github/workflows/vectorize-load-test.yml`:
```yaml
name: Vectorize Search Load Test

on:
  schedule:
    - cron: '0 4 * * 1'   # Weekly on Monday at 04:00 UTC
  workflow_dispatch:

jobs:
  load-test:
    runs-on: ubuntu-latest
    env:
      WORKER_URL: ${{ secrets.VECTORIZE_WORKER_URL }}  # deployed preview Worker

    steps:
      - uses: actions/checkout@v4

      - name: Run k6 Vectorize load test
        uses: grafana/k6-action@v0.3.1
        with:
          filename: k6/vectorize-search-load-test.js
          flags: --out json=k6-vectorize-results.json
        env:
          K6_CLOUD_TOKEN: ${{ secrets.K6_CLOUD_TOKEN }}

      - name: Upload results
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: vectorize-load-results
          path: |
            k6-vectorize-results.json
            k6-vectorize-summary.json
```

## Anti-patterns
- **Embedding a fixed query string** – Vectorize results for repeated identical queries may be
  served from in-network cache, skewing latency measurements. Use a diverse corpus of at least 10
  distinct queries via `SharedArray`.
- **Using `sleep(0)` between iterations** – the Workers AI binding has per-account rate limits;
  zero sleep saturates the embedding service and causes 429 cascades that contaminate load results.
  Use `sleep(0.5)` or higher.
- **Asserting exact score values** – embedding model outputs are deterministic but Vectorize ANN
  results include approximate nearest neighbours; score values vary ±0.01 between runs. Assert on
  floor thresholds, not exact values.
- **Running Vectorize load tests against `wrangler dev --local`** – the local Vectorize stub does
  not replicate HNSW index behaviour or latency; always test against a deployed Worker with a real
  Vectorize index.

## Gotchas
- Vectorize queries count against your account's query-per-second quota (100 QPS on free, higher on
  paid). Exceeding quota causes the Worker to return 429 from the Vectorize binding. Cap VU counts
  accordingly and add a threshold on `http_req_failed` rate.
- The `@cf/baai/bge-small-en-v1.5` model produces 384-dimensional vectors. If you switch models
  (e.g. to `@cf/openai/text-embedding-3-small`), you must re-index your Vectorize index. The load
  test will fail with dimension mismatch errors until you do.
- `SharedArray` data is loaded once and shared across all VUs via copy-on-read; mutations inside
  `export default function` do not persist across iterations. This is correct behaviour — the array
  is read-only.

## Verification
```bash
# Smoke test: 5 VUs for 30 s
WORKER_URL=https://your-worker.workers.dev \
  k6 run --vus 5 --duration 30s k6/vectorize-search-load-test.js

# Full load test (thresholds enforced)
WORKER_URL=https://your-worker.workers.dev k6 run k6/vectorize-search-load-test.js
echo "Exit: $?"   # 0 = all thresholds passed
```

## Related
- `k6-load-testing-cloudflare-workers-api.md`
- `k6-workers-auth-bearer-token-load-test.md`
- `workers-ai-binding-vitest-mocking.md`
- `performance-regression-testing-workers.md`
- `k6-performance-regression-testing.md`

## Sources
- https://developers.cloudflare.com/vectorize/
- https://developers.cloudflare.com/workers-ai/models/
- https://grafana.com/docs/k6/latest/javascript-api/k6-data/sharedarray/
- https://grafana.com/docs/k6/latest/using-k6/thresholds/
- https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/ramping-vus/
