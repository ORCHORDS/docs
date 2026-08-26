# LLM Prompt Compression for KV Cache Efficiency on Workers AI

- Date: 2026-08-22
- Author: example.com
- Status: production

## The Problem: Token Bloat Kills Cache Hit Rates

Long-running AI features accumulate context debt: conversation histories grow unbounded,
system prompts get padded with edge-case instructions, and RAG pipelines paste entire
documents verbatim. The result is that each request looks unique to the KV cache layer —
hit rates collapse toward zero, latency spikes on every turn, and cost scales linearly
with context length instead of sub-linearly.

Workers AI exposes a shared KV cache across requests within the same account. Maximising
hit rates means sending identical (or near-identical) prefix bytes. Prompt compression
keeps the semantic content while shrinking the byte footprint, making prefix collisions
far more likely.

Effective compression combines three techniques: static system-prompt distillation (done
offline, once per model version), selective context truncation (trim the least-relevant
turns at runtime), and dynamic token-budget enforcement via AI Gateway's `max_tokens`
telemetry to detect runaway prompts before they invalidate cached prefixes.

## Context

- Runtime: Cloudflare Workers (ESM, no Node.js compat needed)
- Inference: Workers AI (`@cf/meta/llama-3.1-8b-instruct` or similar)
- Observability: AI Gateway with logging enabled
- Storage: KV namespace for compressed prompt cache, D1 for hit-rate metrics
- Language: TypeScript

## Prompt Distillation at Build Time

Distillation compresses a verbose system prompt into a semantically equivalent but
shorter version using the model itself. Run this offline and store the result; never
distil at request time.

```ts
// scripts/distil-system-prompt.ts
import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic();

async function distilSystemPrompt(verbose: string): Promise<string> {
  const response = await client.messages.create({
    model: "claude-sonnet-4-5",
    max_tokens: 1024,
    messages: [
      {
        role: "user",
        content: `Compress the following system prompt to the minimum tokens needed
to preserve all behavioural constraints and factual grounding.
Remove redundancy, examples, and hedging. Output only the compressed prompt.

<original>${verbose}</original>`,
      },
    ],
  });
  const block = response.content[0];
  if (block.type !== "text") throw new Error("unexpected block type");
  return block.text.trim();
}

// Store result in KV under a content-hash key so Workers can load it
const compressed = await distilSystemPrompt(process.env.SYSTEM_PROMPT!);
console.log(JSON.stringify({ compressed, tokens: compressed.split(" ").length }));
```

## Selective Context Truncation at Runtime

Score each conversation turn by recency and relevance, then drop low-scoring turns until
the total is within a token budget. Keep the system prompt and the most recent user
message immutable — truncation only touches the middle of the conversation.

```ts
// src/compress.ts
export interface Turn {
  role: "user" | "assistant";
  content: string;
  turnIndex: number;
}

function tokenEstimate(text: string): number {
  // ~4 chars per token is a reasonable heuristic for English
  return Math.ceil(text.length / 4);
}

function scoreTurn(turn: Turn, totalTurns: number): number {
  const recency = turn.turnIndex / totalTurns; // 0..1, higher = more recent
  const length = tokenEstimate(turn.content);
  const lengthPenalty = Math.log1p(length) / 10;
  return recency - lengthPenalty;
}

export function compressHistory(
  turns: Turn[],
  budgetTokens: number,
  systemTokens: number
): Turn[] {
  const available = budgetTokens - systemTokens - 256; // reserve for reply
  const scored = turns
    .slice(0, -1) // always keep last user turn
    .map((t) => ({ turn: t, score: scoreTurn(t, turns.length) }))
    .sort((a, b) => b.score - a.score);

  const kept: Turn[] = [turns[turns.length - 1]]; // last turn always kept
  let used = tokenEstimate(kept[0].content);

  for (const { turn } of scored) {
    const cost = tokenEstimate(turn.content);
    if (used + cost <= available) {
      kept.push(turn);
      used += cost;
    }
  }

  return kept.sort((a, b) => a.turnIndex - b.turnIndex);
}
```

## Workers AI Request with Token Budget Enforcement

Route through AI Gateway and parse the usage response to record actual token counts in
D1. A cache hit is detectable when `time_to_first_token` drops below the p50 baseline —
AI Gateway logs expose this in the `cf-aig-cache-status` response header.

```ts
// src/worker.ts
import { compressHistory, Turn } from "./compress";

export interface Env {
  AI: Ai;
  PROMPT_KV: KVNamespace;
  METRICS_DB: D1Database;
  AI_GATEWAY_TOKEN: string;
}

const TOKEN_BUDGET = 4096;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { conversationId, turns } = await request.json<{
      conversationId: string;
      turns: Turn[];
    }>();

    const systemPrompt =
      (await env.PROMPT_KV.get("system:compressed")) ?? "You are a helpful assistant.";
    const systemTokens = Math.ceil(systemPrompt.length / 4);

    const compressedTurns = compressHistory(turns, TOKEN_BUDGET, systemTokens);

    const messages = compressedTurns.map((t) => ({
      role: t.role,
      content: t.content,
    }));

    const result = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
      messages: [{ role: "system", content: systemPrompt }, ...messages],
      max_tokens: 512,
    });

    // Record token usage for cache-hit-rate analysis
    const usage = (result as { usage?: { prompt_tokens: number } }).usage;
    if (usage) {
      await env.METRICS_DB.prepare(
        `INSERT INTO prompt_metrics (conversation_id, prompt_tokens, ts)
         VALUES (?, ?, unixepoch())`
      )
        .bind(conversationId, usage.prompt_tokens, )
        .run();
    }

    return Response.json({ response: (result as { response: string }).response });
  },
};
```

## Measuring Cache Hit Rates via AI Gateway Logs

AI Gateway writes structured logs to Logpush or the dashboard. Query them with a D1
scheduled worker or Logpush → D1 pipeline to compute rolling hit rates.

```ts
// src/cache-metrics.ts — runs as a scheduled Cron Worker
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // Logpush writes AI Gateway events to this D1 table via a transform worker
    const row = await env.METRICS_DB.prepare(`
      SELECT
        COUNT(*) AS total,
        SUM(CASE WHEN cache_status = 'HIT' THEN 1 ELSE 0 END) AS hits,
        ROUND(AVG(ttft_ms), 1) AS avg_ttft_ms
      FROM ai_gateway_events
      WHERE ts > unixepoch() - 3600
    `).first<{ total: number; hits: number; avg_ttft_ms: number }>();

    if (!row) return;
    const hitRate = row.total > 0 ? row.hits / row.total : 0;
    console.log(
      JSON.stringify({ hitRate, avg_ttft_ms: row.avg_ttft_ms, window: "1h" })
    );

    // Alert if hit rate drops below threshold
    if (hitRate < 0.3) {
      console.warn("KV cache hit rate below 30% — review prompt compression strategy");
    }
  },
};
```

## Anti-patterns

- Compressing prompts at request time using a second LLM call — adds latency that negates
  the cache benefit; do it offline.
- Truncating the system prompt between requests — prefix must be byte-identical for the
  KV cache to match; any dynamic injection breaks the prefix.
- Using `Math.random()` or timestamps inside the system prompt — makes every request
  unique and defeats caching entirely.
- Setting `max_tokens` so high that it dominates the prompt budget; the effective context
  shrinks with nothing to show for it.

## Gotchas

- Workers AI KV cache keys on the full prompt bytes including model ID — even a single
  extra space in the system prompt creates a new cache entry.
- `tokenEstimate` (chars/4) diverges for code, JSON, or CJK text; use a real tokenizer
  (`tiktoken-node` or a Wasm port) in production for accurate budgeting.
- AI Gateway `cf-aig-cache-status` header is only present when caching is explicitly
  enabled on the gateway route; it defaults to off.
- D1 `INSERT` in the hot path adds ~2 ms RTT; batch inserts or use a Queue consumer
  to write metrics asynchronously.

## Verification

```ts
// test/compress.test.ts
import { compressHistory, Turn } from "../src/compress";

const turns: Turn[] = Array.from({ length: 20 }, (_, i) => ({
  role: i % 2 === 0 ? "user" : "assistant",
  content: "word ".repeat(50), // ~50 tokens each
  turnIndex: i,
}));

const result = compressHistory(turns, 512, 64);
const totalTokens = result.reduce(
  (sum, t) => sum + Math.ceil(t.content.length / 4),
  0
);
console.assert(totalTokens <= 512 - 64 - 256, "budget exceeded");
console.assert(result[result.length - 1].turnIndex === 19, "last turn missing");
console.log("compress test passed, kept", result.length, "of", turns.length, "turns");
```

## Related

- [AI Gateway Caching](ai-gateway-caching.md)
- [AI Gateway Logging](ai-gateway-logging.md)
- [Context Engineering Systems](context-engineering-systems.md)
- [AI Latency Optimization](ai-latency-optimization.md)
- [Workers AI Streaming Inference](cloudflare-workers-ai-streaming-inference.md)

## Sources

- https://developers.cloudflare.com/ai-gateway/
- https://developers.cloudflare.com/workers-ai/
- https://developers.cloudflare.com/workers-ai/models/
- https://arxiv.org/abs/2310.06839 — LLMLingua prompt compression paper
- https://developers.cloudflare.com/d1/
