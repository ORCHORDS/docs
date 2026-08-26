# k6 Workers R2 Object Storage Load Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You expose an R2 bucket through a Cloudflare Worker — GET for downloads, PUT for uploads, perhaps presigned-URL generation — and need to know how the Worker behaves under concurrent read/write load before you go to production. You want to catch CPU-time overruns, measure p95 latency for small vs. large objects, and find the concurrency level at which the Worker starts returning 503s or timing out.

## Context

Cloudflare R2 is an S3-compatible object store with no egress fees. Workers access R2 through a bucket binding (`env.BUCKET`) rather than HTTP; the cost model is per-operation rather than per-byte-transferred. Load testing a Worker-over-R2 path differs from a plain API test: the Worker CPU budget is per-request, R2 has its own per-bucket rate limits (class A: 1000 ops/s, class B: 10 000 ops/s), and multipart uploads have their own concurrency model. k6 is well-suited because its virtual-user model maps cleanly onto concurrent Worker requests.

## Seeding the bucket before the load test

```bash
# Seed 100 objects of varying sizes using wrangler
for i in $(seq 1 100); do
  dd if=/dev/urandom bs=1k count=$((i % 50 + 1)) 2>/dev/null | \
    wrangler r2 object put load-test-bucket/obj-${i}.bin --file /dev/stdin
done
```

```ts
// Alternatively, use a k6 setup() function to seed via the Worker PUT endpoint
export function setup() {
  for (let i = 0; i < 20; i++) {
    const body = new ArrayBuffer(1024 * (i + 1)); // 1–20 KB
    const res = http.put(`${BASE_URL}/objects/seed-${i}.bin`, body, {
      headers: { "Content-Type": "application/octet-stream" },
    });
    check(res, { "seed upload 200": (r) => r.status === 200 });
  }
}
```

## k6 script: mixed read/write workload

```ts
// k6/r2-load-test.ts
import http from "k6/http";
import { check, sleep } from "k6";
import { Trend, Counter } from "k6/metrics";
import { randomIntBetween } from "https://jslib.k6.io/k6-utils/1.4.0/index.js";

const BASE_URL = __ENV.WORKER_URL ?? "https://my-worker.example.com";
const OBJECT_COUNT = 20;

const getLatency = new Trend("r2_get_latency", true);
const putLatency = new Trend("r2_put_latency", true);
const errorCount = new Counter("r2_errors");

export const options = {
  scenarios: {
    // 80% reads
    readers: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "30s", target: 50 },
        { duration: "60s", target: 50 },
        { duration: "20s", target: 0 },
      ],
    },
    // 20% writes at lower concurrency
    writers: {
      executor: "constant-vus",
      vus: 10,
      duration: "110s",
    },
  },
  thresholds: {
    r2_get_latency: ["p(95)<800"],   // 800 ms p95 for GET
    r2_put_latency: ["p(95)<2000"],  // 2 s p95 for PUT
    r2_errors: ["count<50"],
    http_req_failed: ["rate<0.01"],
  },
};

export default function () {
  const isWrite = Math.random() < 0.2;

  if (isWrite) {
    const key = `stress-${__VU}-${Date.now()}.bin`;
    const sizeKb = randomIntBetween(1, 128);
    const body = new ArrayBuffer(sizeKb * 1024);
    const start = Date.now();

    const res = http.put(`${BASE_URL}/objects/${key}`, body, {
      headers: { "Content-Type": "application/octet-stream" },
    });

    putLatency.add(Date.now() - start);
    const ok = check(res, { "put 200": (r) => r.status === 200 });
    if (!ok) errorCount.add(1);
  } else {
    const idx = randomIntBetween(0, OBJECT_COUNT - 1);
    const start = Date.now();

    const res = http.get(`${BASE_URL}/objects/seed-${idx}.bin`);

    getLatency.add(Date.now() - start);
    const ok = check(res, {
      "get 200": (r) => r.status === 200,
      "non-empty body": (r) => (r.body as ArrayBuffer).byteLength > 0,
    });
    if (!ok) errorCount.add(1);
  }

  sleep(0.1);
}
```

## Worker: R2 GET and PUT handlers

```ts
// src/index.ts
interface Env {
  BUCKET: R2Bucket;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const key = url.pathname.replace(/^\/objects\//, "");

    if (!key) return new Response("Missing key", { status: 400 });

    if (request.method === "GET") {
      const object = await env.BUCKET.get(key);
      if (!object) return new Response("Not Found", { status: 404 });

      const headers = new Headers();
      object.writeHttpMetadata(headers);
      headers.set("etag", object.httpEtag);

      return new Response(object.body, { headers });
    }

    if (request.method === "PUT") {
      await env.BUCKET.put(key, request.body, {
        httpMetadata: { contentType: request.headers.get("Content-Type") ?? "application/octet-stream" },
      });
      return new Response(null, { status: 200 });
    }

    return new Response("Method Not Allowed", { status: 405 });
  },
} satisfies ExportedHandler<Env>;
```

## k6 scenario: presigned-URL throughput

```ts
// k6/presigned-url-load.ts
import http from "k6/http";
import { check } from "k6";

const BASE_URL = __ENV.WORKER_URL;

export const options = {
  vus: 30,
  duration: "60s",
  thresholds: {
    http_req_duration: ["p(95)<500"], // presigned URL generation should be fast
    http_req_failed: ["rate<0.005"],
  },
};

export default function () {
  // Step 1: get a presigned URL from the Worker
  const signRes = http.post(`${BASE_URL}/presign`, JSON.stringify({ key: "upload.bin", ttl: 300 }), {
    headers: { "Content-Type": "application/json" },
  });

  check(signRes, {
    "presign 200": (r) => r.status === 200,
    "has url": (r) => !!JSON.parse(r.body as string).url,
  });

  if (signRes.status !== 200) return;

  // Step 2: upload directly to R2 using the presigned URL (bypasses the Worker)
  const { url } = JSON.parse(signRes.body as string);
  const uploadRes = http.put(url, new ArrayBuffer(512), {
    headers: { "Content-Type": "application/octet-stream" },
  });

  check(uploadRes, { "direct put 200": (r) => r.status === 200 });
}
```

## Anti-patterns

- **Using `wrangler dev` (local) as the load target** — local Miniflare does not replicate R2 throughput limits or network latency; always point k6 at a deployed Worker.
- **Omitting `teardown()` to delete seeded objects** — accumulated test objects inflate billing; delete them in a `teardown` function or use a dedicated test bucket cleaned via a lifecycle rule.
- **Using a single VU for GET and PUT in sequence** — this serialises reads and writes, hiding the contention that exposes bugs. Run them as separate scenarios with concurrent VUs.
- **Asserting only HTTP 200** — R2 rate-limit errors come back as 429 from the Worker if you propagate them, or as 500 if you don't. Check both and add a `r2_errors` counter to surface them separately.

## Gotchas

- R2 class A operations (PUT, DELETE, list) are rate-limited at 1000 ops/s per bucket. A k6 script with 100 VUs each writing every 100 ms can saturate this; add `sleep(randomIntBetween(50, 200) / 1000)` jitter to the writers scenario.
- Large GET responses in k6 are read as `ArrayBuffer` when using `http.get` with `responseType: "binary"`. The default `responseType: "text"` decodes binary bodies and inflates reported sizes.
- Workers have a 6MB subrequest body limit for R2 `put()`. Objects larger than 6 MB must use the multipart upload API; the load test should match your production object size distribution.
- `object.body` on an R2 object is a `ReadableStream`. Returning it directly in the `Response` constructor streams it efficiently; calling `.arrayBuffer()` first buffers the whole object in the Worker's memory and inflates CPU time.

## Verification

```bash
# Dry-run against wrangler dev (sanity only, not representative)
k6 run --env WORKER_URL=http://localhost:8787 k6/r2-load-test.ts

# Real load run against deployed Worker
k6 run --env WORKER_URL=https://my-worker.example.com \
       --out json=results.json \
       k6/r2-load-test.ts

# Summarise key metrics
k6 run ... | grep -E "r2_(get|put)_latency|r2_errors"
```

Expected: `r2_get_latency p(95) < 800 ms`, `r2_put_latency p(95) < 2000 ms`, `r2_errors < 50` over the full run.

## Related

- `k6-workers-api-pagination-load-testing.md`
- `k6-load-testing-cloudflare-workers-api.md`
- `vitest-r2-multipart-upload-testing.md`
- `vitest-workers-r2-presigned-url-expiry-testing.md`
- `r2-bucket-miniflare-testing.md`

## Sources

- Cloudflare Docs — R2 Workers binding: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- Cloudflare Docs — R2 limits: https://developers.cloudflare.com/r2/reference/limits/
- k6 Docs — Scenarios / ramping-vus executor: https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/ramping-vus/
- k6 Docs — Custom metrics (Trend, Counter): https://grafana.com/docs/k6/latest/using-k6/metrics/create-custom-metrics/
