# k6 Workers AI Gateway Load Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker routes LLM requests through Cloudflare AI Gateway to add caching, rate limiting, and observability, and you need to validate two things before launch: (1) that the Gateway's caching layer actually reduces upstream inference latency under repeated identical prompts, and (2) that your Worker handles Gateway rate-limit responses (`429`) and upstream timeouts gracefully at realistic concurrency. Unit tests with mocked bindings don't cover the routing or retry logic; you need a k6 load test against the deployed stack.

## Context

Cloudflare AI Gateway sits between your Worker and a backing AI provider (Workers AI, OpenAI, Anthropic, etc.). It transparently caches identical requests (same model + body SHA), enforces per-gateway rate limits, logs requests, and surfaces analytics. A Worker calling the Gateway through a `GatewayBinding` uses the `env.AI_GATEWAY.run()` method (Workers AI binding variant) or a regular `fetch()` to the Gateway URL. k6 can target either entry point — the Worker's own HTTP endpoint is preferred for full end-to-end coverage of the Worker logic, rate-limit header handling, and retry behaviour.

## Worker: forwarding requests through AI Gateway with retry

```ts
// src/index.ts
interface Env {
  AI: Ai;
  AI_GATEWAY_ID: string; // set in wrangler.toml [vars]
}

const MAX_RETRIES = 2;
const RETRY_DELAY_MS = 500;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("POST only", { status: 405 });

    const { prompt, model = "@cf/meta/llama-3-8b-instruct" } = await request.json<{
      prompt: string;
      model?: string;
    }>();

    let lastError: unknown;

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const result = await env.AI.run(model as Parameters<typeof env.AI.run>[0], {
          prompt,
          gateway: { id: env.AI_GATEWAY_ID, skipCache: false },
        });

        return Response.json({ result, attempt });
      } catch (err: unknown) {
        lastError = err;
        const status = (err as { status?: number }).status;
        if (status === 429 || status === 503) {
          await new Promise((r) => setTimeout(r, RETRY_DELAY_MS * (attempt + 1)));
          continue;
        }
        break;
      }
    }

    return Response.json({ error: String(lastError) }, { status: 502 });
  },
} satisfies ExportedHandler<Env>;
```

## k6: cache-hit ratio and latency split test

```ts
// k6/ai-gateway-cache-load.ts
import http from "k6/http";
import { check, sleep } from "k6";
import { Trend, Rate, Counter } from "k6/metrics";

const BASE_URL = __ENV.WORKER_URL;
const UNIQUE_PROMPTS = 5; // small pool → high cache-hit probability

const cacheHitLatency  = new Trend("ai_cache_hit_latency_ms",  true);
const cacheMissLatency = new Trend("ai_cache_miss_latency_ms", true);
const cacheHitRate     = new Rate("ai_cache_hit_rate");
const retryCount       = new Counter("ai_retry_count");

export const options = {
  scenarios: {
    steady: {
      executor: "constant-vus",
      vus: 20,
      duration: "90s",
    },
  },
  thresholds: {
    ai_cache_hit_latency_ms:  ["p(95)<500"],   // cached responses should be fast
    ai_cache_miss_latency_ms: ["p(95)<8000"],  // cold inference budget
    ai_cache_hit_rate:        ["rate>0.60"],   // expect >60 % hits after warm-up
    http_req_failed:          ["rate<0.05"],
  },
};

export default function () {
  const promptIndex = Math.floor(Math.random() * UNIQUE_PROMPTS);
  const prompt = `Summarise the capital city of country number ${promptIndex} in one sentence.`;

  const payload = JSON.stringify({ prompt });
  const start = Date.now();

  const res = http.post(BASE_URL, payload, {
    headers: { "Content-Type": "application/json" },
    timeout: "15s",
  });

  const elapsed = Date.now() - start;

  const fromCache = res.headers["Cf-Cache-Status"] === "HIT";
  cacheHitRate.add(fromCache ? 1 : 0);

  if (fromCache) {
    cacheHitLatency.add(elapsed);
  } else {
    cacheMissLatency.add(elapsed);
  }

  const body = JSON.parse(res.body as string);
  if (body.attempt && body.attempt > 0) retryCount.add(body.attempt);

  check(res, {
    "status 200": (r) => r.status === 200,
    "has result": () => !!body.result,
  });

  sleep(0.5);
}
```

## k6: rate-limit resilience scenario

```ts
// k6/ai-gateway-rate-limit.ts
import http from "k6/http";
import { check } from "k6";
import { Counter, Rate } from "k6/metrics";

const BASE_URL = __ENV.WORKER_URL;

const rateLimited   = new Counter("ai_rate_limited_requests");
const retrySuccess  = new Rate("ai_retry_succeeded");

export const options = {
  // Spike to deliberately trigger Gateway rate limiting
  scenarios: {
    spike: {
      executor: "ramping-arrival-rate",
      startRate: 10,
      timeUnit: "1s",
      preAllocatedVUs: 50,
      maxVUs: 100,
      stages: [
        { duration: "10s", target: 10  },
        { duration: "20s", target: 200 }, // spike well above Gateway rate limit
        { duration: "20s", target: 10  },
      ],
    },
  },
  thresholds: {
    // Worker must not expose raw 429s to clients — it should retry and return 200 or 502
    "http_req_failed{expected_response:false}": ["rate<0.10"],
    ai_rate_limited_requests: ["count>0"], // confirm we actually hit the limit
  },
};

export default function () {
  const res = http.post(
    BASE_URL,
    JSON.stringify({ prompt: "Say hi." }),
    { headers: { "Content-Type": "application/json" }, timeout: "20s" }
  );

  const body = JSON.parse((res.body as string) || "{}");

  if (res.status === 429) {
    rateLimited.add(1);
  }

  // Worker should absorb 429s via retry; expect 200 or handled 502 — not raw 429
  check(res, {
    "not raw 429": (r) => r.status !== 429,
  });

  const succeeded = res.status === 200 && !!body.result;
  retrySuccess.add(succeeded ? 1 : 0);
}
```

## k6: streaming response latency (time-to-first-token proxy)

```ts
// k6/ai-gateway-streaming.ts
import http from "k6/http";
import { check } from "k6";
import { Trend } from "k6/metrics";

const BASE_URL = __ENV.WORKER_URL;
const ttftMetric = new Trend("ai_time_to_first_token_ms", true);

export const options = {
  vus: 5,
  duration: "60s",
  thresholds: {
    ai_time_to_first_token_ms: ["p(90)<3000"],
  },
};

export default function () {
  // k6 does not support streaming responses natively, so TTFT is approximated
  // as the time until the Worker begins writing the response body. Use a
  // Worker endpoint that flushes the first token immediately via ReadableStream.
  const start = Date.now();

  const res = http.post(
    `${BASE_URL}/stream`,
    JSON.stringify({ prompt: "Count to 3.", stream: true }),
    {
      headers: { "Content-Type": "application/json" },
      responseType: "text",
    }
  );

  const elapsed = Date.now() - start;
  ttftMetric.add(elapsed); // full response time as TTFT proxy

  check(res, {
    "status 200": (r) => r.status === 200,
    "body non-empty": (r) => (r.body as string).length > 0,
  });
}
```

## Anti-patterns

- **Targeting the AI Gateway URL directly in k6** — bypass the Worker and you skip the retry logic, auth checks, and header transformation your production code performs. Always load-test via the Worker's own endpoint.
- **Using unique prompts for every VU iteration** — unique prompts defeat Gateway caching. Use a small fixed prompt pool if you want to measure cache hit ratios; only use unique prompts when testing cold-path latency specifically.
- **Treating `Cf-Cache-Status: HIT` as proof of correctness** — the cache key includes the full request body and model; a single-character change in the prompt is a cache miss. Verify that your prompt normalisation (trimming, lowercasing) happens before the Gateway call if cache hit rate matters.
- **Running the spike scenario without a safety threshold** — unthrottled k6 spikes can exhaust your AI provider quota and generate real billing. Set a `maxVUs` ceiling and run against a test gateway with a low rate limit during development.

## Gotchas

- `Cf-Cache-Status` is only present in the Gateway's own response headers, not necessarily propagated by the Worker. Add `response.headers.set("Cf-Cache-Status", upstream.headers.get("Cf-Cache-Status") ?? "MISS")` in your Worker if you want k6 to observe it.
- AI Gateway caches based on a SHA of the request body. If your Worker adds a `request_id` or timestamp to the upstream payload, every request is a cache miss even with identical user prompts. Strip ephemeral fields before forwarding.
- k6 `timeout` on `http.post` is the full response time. For streaming inference, set this to at least 2× your expected p99 generation time or VUs will accumulate and skew VU utilisation.
- Gateway rate limits are per-gateway, not per-Worker. Multiple Workers sharing a gateway share the limit bucket; factor this in when interpreting `ai_rate_limited_requests` counts.

## Verification

```bash
# Warm the cache first (5 prompts × 3 primes each)
for i in 0 1 2 3 4; do
  for j in 1 2 3; do
    curl -s -X POST "$WORKER_URL" \
      -H "Content-Type: application/json" \
      -d "{\"prompt\":\"Summarise the capital city of country number ${i} in one sentence.\"}" \
      > /dev/null
  done
done

# Run the cache-hit ratio test
k6 run --env WORKER_URL="$WORKER_URL" k6/ai-gateway-cache-load.ts

# Run the rate-limit resilience test (lower VUs in dev)
k6 run --env WORKER_URL="$WORKER_URL" \
       --vus 20 \
       k6/ai-gateway-rate-limit.ts
```

Expected: `ai_cache_hit_rate > 60 %`, `ai_cache_hit_latency_ms p(95) < 500 ms`, `not raw 429` check passes for all requests.

## Related

- `k6-load-testing-cloudflare-workers-api.md`
- `k6-workers-rate-limiter-load-test.md`
- `vitest-workers-ai-gateway-mock-testing.md`
- `miniflare-workers-ai-binding-mock-structured-output.md`
- `workers-ai-binding-vitest-mocking.md`

## Sources

- Cloudflare Docs — AI Gateway overview: https://developers.cloudflare.com/ai-gateway/
- Cloudflare Docs — AI Gateway caching: https://developers.cloudflare.com/ai-gateway/configuration/caching/
- Cloudflare Docs — AI Gateway rate limiting: https://developers.cloudflare.com/ai-gateway/configuration/rate-limiting/
- k6 Docs — ramping-arrival-rate executor: https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/ramping-arrival-rate/
- k6 Docs — Custom metrics: https://grafana.com/docs/k6/latest/using-k6/metrics/create-custom-metrics/
