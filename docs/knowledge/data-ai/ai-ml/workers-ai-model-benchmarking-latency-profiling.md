# Workers AI Model Benchmarking and Latency Profiling

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

You've chosen a Workers AI model based on documentation specs but the p99 latency in
production is 4 × higher than expected. You don't know whether the bottleneck is
time-to-first-token (TTFT), generation speed (tokens/s), network round-trip, or cold
starts. Before committing a model to production—or before deciding between
`@cf/meta/llama-3.1-8b-instruct` and a quantised alternative—you need reproducible,
comparable latency numbers collected from inside a Worker under realistic conditions.

## Context

Workers AI inference latency has several distinct components:

| Component          | Description                                              | Typical range       |
|--------------------|----------------------------------------------------------|---------------------|
| TTFT               | Time from request to first token (includes model load)   | 200 ms – 2 s        |
| Generation latency | Time to generate all output tokens after TTFT            | tokens × ~20–50 ms  |
| Worker CPU         | Input preparation, JSON encode/decode in the Worker      | < 5 ms              |
| Network round-trip | Client → Cloudflare edge → Worker → AI worker → back     | 10–100 ms           |

Cold starts inflate TTFT by up to 2 s when a model has not been used recently.
The free tier has stricter cold-start frequency; the paid/serverless tier keeps models
warmer but does not guarantee zero cold starts.

Benchmarking strategy:
1. Measure TTFT separately from total latency.
2. Use streaming to capture TTFT without waiting for full generation.
3. Run N ≥ 30 iterations per configuration to get stable percentiles.
4. Write results to D1 for analysis; expose a summary endpoint.

## Benchmark Worker: Measuring TTFT and Total Latency

```typescript
// src/benchmark.ts
export interface Env {
  AI: Ai;
  DB: D1Database;
}

export interface BenchmarkConfig {
  model: string;
  promptTokens: number;   // approximate; controls prompt size
  maxOutputTokens: number;
  iterations: number;
  tag: string;            // label for this run, e.g. "llama-8b-q4-warm"
}

const FILLER_WORDS = "the quick brown fox jumps over the lazy dog ".repeat(50);

/** Build a prompt of approximately `targetTokens` tokens. */
function buildPrompt(targetTokens: number): string {
  // ~1.3 chars/token heuristic for English
  return FILLER_WORDS.slice(0, Math.floor(targetTokens * 1.3));
}

/** Measure a single streaming inference call. */
async function measureOne(
  model: string,
  prompt: string,
  maxTokens: number,
  ai: Ai,
): Promise<{ ttftMs: number; totalMs: number; outputTokens: number }> {
  const start = Date.now();
  let ttftMs = -1;
  let outputTokens = 0;

  const stream = await ai.run(model, {
    messages: [{ role: "user", content: prompt }],
    max_tokens: maxTokens,
    stream: true,
  }) as ReadableStream;

  const reader = stream.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value, { stream: true });

    // SSE lines: "data: {...}\n\n"
    for (const line of chunk.split("\n")) {
      if (!line.startsWith("data: ")) continue;
      const json = line.slice(6).trim();
      if (json === "[DONE]") break;

      try {
        const parsed = JSON.parse(json) as {
          response?: string;
          p?: string;       // some models use "p"
        };
        const token = parsed.response ?? parsed.p ?? "";
        if (token && ttftMs < 0) {
          ttftMs = Date.now() - start;
        }
        if (token) outputTokens += 1;
      } catch {
        // skip malformed SSE lines
      }
    }
  }

  return {
    ttftMs: ttftMs < 0 ? Date.now() - start : ttftMs,
    totalMs: Date.now() - start,
    outputTokens,
  };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("POST a BenchmarkConfig JSON body", { status: 405 });
    }

    const config = (await request.json()) as BenchmarkConfig;
    const {
      model,
      promptTokens = 50,
      maxOutputTokens = 128,
      iterations = 10,
      tag,
    } = config;

    const prompt = buildPrompt(promptTokens);
    const results: { ttftMs: number; totalMs: number; outputTokens: number }[] = [];

    for (let i = 0; i < iterations; i++) {
      // Small pause between runs to avoid rate-limit bursts
      if (i > 0) await new Promise((r) => setTimeout(r, 500));
      const r = await measureOne(model, prompt, maxOutputTokens, env.AI);
      results.push(r);
    }

    // Compute percentiles
    const sort = (arr: number[]) => [...arr].sort((a, b) => a - b);
    const pct = (sorted: number[], p: number) =>
      sorted[Math.floor(sorted.length * p / 100)];

    const ttfts  = sort(results.map((r) => r.ttftMs));
    const totals = sort(results.map((r) => r.totalMs));
    const toks   = results.map((r) => r.outputTokens);
    const avgToks = toks.reduce((a, b) => a + b, 0) / toks.length;
    const avgTotal = totals.reduce((a, b) => a + b, 0) / totals.length;
    const tokensPerSec = avgToks / (avgTotal / 1000);

    const summary = {
      tag,
      model,
      iterations,
      promptTokens,
      maxOutputTokens,
      ttft:  { p50: pct(ttfts, 50), p90: pct(ttfts, 90), p99: pct(ttfts, 99) },
      total: { p50: pct(totals, 50), p90: pct(totals, 90), p99: pct(totals, 99) },
      avgOutputTokens: Math.round(avgToks),
      tokensPerSec: Math.round(tokensPerSec),
    };

    // Persist to D1 for trend analysis
    await env.DB.prepare(
      `INSERT INTO benchmark_runs
       (tag, model, iterations, prompt_tokens, max_output_tokens,
        ttft_p50, ttft_p90, ttft_p99,
        total_p50, total_p90, total_p99,
        avg_output_tokens, tokens_per_sec, run_at)
       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,unixepoch())`,
    ).bind(
      tag, model, iterations, promptTokens, maxOutputTokens,
      summary.ttft.p50, summary.ttft.p90, summary.ttft.p99,
      summary.total.p50, summary.total.p90, summary.total.p99,
      summary.avgOutputTokens, summary.tokensPerSec,
    ).run();

    return Response.json(summary, { status: 200 });
  },
};
```

D1 schema:

```sql
-- migrations/0001_benchmark_runs.sql
CREATE TABLE IF NOT EXISTS benchmark_runs (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  tag                TEXT NOT NULL,
  model              TEXT NOT NULL,
  iterations         INTEGER NOT NULL,
  prompt_tokens      INTEGER NOT NULL,
  max_output_tokens  INTEGER NOT NULL,
  ttft_p50           INTEGER,
  ttft_p90           INTEGER,
  ttft_p99           INTEGER,
  total_p50          INTEGER,
  total_p90          INTEGER,
  total_p99          INTEGER,
  avg_output_tokens  REAL,
  tokens_per_sec     REAL,
  run_at             INTEGER NOT NULL
);
```

## Model Comparison Script

```bash
#!/usr/bin/env bash
# scripts/compare-models.sh
set -euo pipefail

WORKER_URL="https://bench.example.workers.dev"
ITERATIONS=30

models=(
  "llama-8b-q8"
  "llama-8b-q4"
  "mistral-7b"
)
configs=(
  '{"model":"@cf/meta/llama-3.1-8b-instruct","promptTokens":100,"maxOutputTokens":128,"iterations":'"$ITERATIONS"',"tag":"llama-8b-q8"}'
  '{"model":"@cf/meta/llama-3.2-3b-instruct","promptTokens":100,"maxOutputTokens":128,"iterations":'"$ITERATIONS"',"tag":"llama-3b-q4"}'
  '{"model":"@cf/mistral/mistral-7b-instruct-v0.1","promptTokens":100,"maxOutputTokens":128,"iterations":'"$ITERATIONS"',"tag":"mistral-7b"}'
)

for i in "${!models[@]}"; do
  echo "=== Benchmarking: ${models[$i]} ==="
  curl -s -X POST "$WORKER_URL" \
    -H "Content-Type: application/json" \
    -d "${configs[$i]}" | jq '{model,ttft,total,tokensPerSec}'
  sleep 5   # cooldown between model switches
done
```

## Trend Monitoring Endpoint

```typescript
// src/trends.ts — query D1 for latency regressions
export default {
  async fetch(request: Request, env: Env & { DB: D1Database }): Promise<Response> {
    const url   = new URL(request.url);
    const model = url.searchParams.get("model") ?? "%";
    const days  = parseInt(url.searchParams.get("days") ?? "7", 10);

    const { results } = await env.DB.prepare(
      `SELECT tag, model,
              AVG(ttft_p50)    AS avg_ttft_p50,
              AVG(ttft_p99)    AS avg_ttft_p99,
              AVG(total_p50)   AS avg_total_p50,
              AVG(total_p99)   AS avg_total_p99,
              AVG(tokens_per_sec) AS avg_tps,
              COUNT(*)         AS runs,
              MIN(run_at)      AS first_seen,
              MAX(run_at)      AS last_seen
       FROM benchmark_runs
       WHERE model LIKE ?
         AND run_at >= unixepoch() - ?
       GROUP BY tag, model
       ORDER BY last_seen DESC`,
    ).bind(model, days * 86400).all();

    return Response.json({ period_days: days, models: results });
  },
};
```

## Anti-patterns

- **Benchmarking from the browser or external network**: network latency and connection
  setup inflate numbers. Benchmark from a Worker or use `wrangler dev` with `--local`
  overrides to isolate model latency.
- **Using `max_tokens = 1` to measure TTFT only**: forcing one output token doesn't
  reflect real-world generation setup overhead. Measure TTFT via streaming with
  realistic output lengths.
- **Comparing models at different temperature or sampling settings**: set `temperature`,
  `top_p`, etc. identically across models to isolate the model variable.
- **Treating cold-start runs as steady-state**: the first 1–3 runs of any benchmark
  session are cold; discard them or mark them separately.
- **Persisting raw token strings**: benchmark tables should store timing statistics only,
  not the generated text—this keeps the table small and avoids PII storage issues.

## Gotchas

- **SSE format varies by model**: some Workers AI models return `data: {"response":"tok"}`
  while others use `data: {"p":"tok"}` or OpenAI-compatible `data: {"choices":[...]}`.
  The parser above handles common variants but validate against each model's actual
  stream output.
- **Workers AI streaming requires `stream: true`** in the `run()` options AND the
  returned value must be consumed as a `ReadableStream`. If you don't call
  `getReader()` and drain it, the underlying fetch hangs.
- **Concurrency inflates latency**: Workers AI shares GPU capacity across accounts.
  Running benchmarks during off-peak hours (weekday nights UTC) gives lower and more
  stable numbers than peak hours.
- **D1 write latency affects `totalMs` measurement**: the D1 persist step runs *after*
  the timing calculation, so it doesn't contaminate the timing numbers in this design.
  Confirm your measurement window ends before any I/O.
- **`setTimeout` inside Workers**: `setTimeout` inside a Workers `fetch()` handler
  requires the `nodejs_compat` compatibility flag. Alternatively, use `await scheduler.wait(ms)`.

## Verification

```bash
# Run a quick 5-iteration benchmark
curl -s -X POST https://bench.example.workers.dev \
  -H "Content-Type: application/json" \
  -d '{
    "model": "@cf/meta/llama-3.1-8b-instruct",
    "promptTokens": 50,
    "maxOutputTokens": 64,
    "iterations": 5,
    "tag": "sanity-check"
  }' | jq '{ttft,total,tokensPerSec}'

# Query trends for the last 7 days
curl -s "https://bench.example.workers.dev/trends?days=7" | jq .

# Check D1 rows directly
wrangler d1 execute inference-results \
  --command "SELECT tag, avg_ttft_p50, avg_total_p99, avg_tps FROM benchmark_runs ORDER BY last_seen DESC LIMIT 5"

# Compare two tags side-by-side
wrangler d1 execute inference-results \
  --command "SELECT tag, ttft_p50, ttft_p99, total_p50, total_p99, tokens_per_sec FROM benchmark_runs WHERE tag IN ('llama-8b-q8','mistral-7b') ORDER BY run_at DESC LIMIT 10"
```

## Related

- `ai-latency-optimization.md`
- `ai-cold-start-patterns.md`
- `ai-model-selection-workers-ai-inference.md`
- `cloudflare-workers-ai-streaming-inference.md`
- `llm-quantization-tradeoffs-q4-q8.md`
- `llm-token-counting.md`
- `llm-ab-testing.md`

## Sources

- Workers AI models and limits: https://developers.cloudflare.com/workers-ai/models/
- Workers AI streaming: https://developers.cloudflare.com/workers-ai/features/streaming/
- Workers AI platform limits: https://developers.cloudflare.com/workers-ai/platform/limits/
- D1 client API: https://developers.cloudflare.com/d1/build-with-d1/d1-client-api/
- `scheduler.wait()` in Workers: https://developers.cloudflare.com/workers/runtime-apis/scheduler/
