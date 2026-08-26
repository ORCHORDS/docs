# Workers AI Tool Calling / Function Dispatch

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need an LLM to take actions — look up a price, query a database, call an external API — rather than just generate text. Workers AI exposes a `tools` parameter on supported models (Llama 3.1) that returns structured `tool_calls` you can dispatch to typed TypeScript handlers and then feed the results back to the model in a second turn.

---

## Context

`@cf/meta/llama-3.1-8b-instruct` supports OpenAI-compatible tool calling via `env.AI.run`. The model responds with a `tool_calls` array instead of `content` when it decides a tool should be invoked. Your Worker is responsible for dispatching those calls to real functions, collecting the results, and appending them as `role: "tool"` messages before making the follow-up completion request. KV caching of deterministic tool results (e.g., product lookups) prevents redundant AI calls and cuts latency. The entire round-trip fits inside a single Worker request with no Durable Object needed.

---

## Section 1 — Wrangler Config

```toml
# wrangler.toml
name = "ai-tool-dispatch"
main = "src/index.ts"
compatibility_date = "2025-04-01"

[ai]
binding = "AI"

[[kv_namespaces]]
binding = "TOOL_CACHE"
id = "<your-kv-namespace-id>"
```

---

## Section 2 — Tool Schema and Handler Map

```typescript
// src/tools.ts
import type { Env } from "./index";

export interface ToolCall {
  id: string;
  type: "function";
  function: { name: string; arguments: string };
}

export interface ToolResult {
  role: "tool";
  tool_call_id: string;
  content: string;
}

// ---- tool definitions sent to the model ----
export const TOOLS = [
  {
    type: "function" as const,
    function: {
      name: "get_product_price",
      description: "Return the current price of a product by SKU.",
      parameters: {
        type: "object",
        properties: {
          sku: { type: "string", description: "Product SKU" },
        },
        required: ["sku"],
      },
    },
  },
  {
    type: "function" as const,
    function: {
      name: "check_inventory",
      description: "Return the in-stock quantity for a SKU.",
      parameters: {
        type: "object",
        properties: {
          sku: { type: "string" },
          warehouse: { type: "string", enum: ["us-east", "eu-west"] },
        },
        required: ["sku"],
      },
    },
  },
];

// ---- typed handler functions ----
type HandlerFn = (args: Record<string, unknown>, env: Env) => Promise<string>;

async function getProductPrice(
  { sku }: { sku: string },
  env: Env
): Promise<string> {
  const cacheKey = `price:${sku}`;
  const cached = await env.TOOL_CACHE.get(cacheKey);
  if (cached) return cached;

  // Replace with your real price source
  const price = (Math.random() * 100 + 1).toFixed(2);
  const result = JSON.stringify({ sku, price, currency: "USD" });

  await env.TOOL_CACHE.put(cacheKey, result, { expirationTtl: 300 });
  return result;
}

async function checkInventory(
  { sku, warehouse = "us-east" }: { sku: string; warehouse?: string },
  env: Env
): Promise<string> {
  const cacheKey = `inv:${sku}:${warehouse}`;
  const cached = await env.TOOL_CACHE.get(cacheKey);
  if (cached) return cached;

  const qty = Math.floor(Math.random() * 500);
  const result = JSON.stringify({ sku, warehouse, quantity: qty });

  await env.TOOL_CACHE.put(cacheKey, result, { expirationTtl: 60 });
  return result;
}

const HANDLERS: Record<string, HandlerFn> = {
  get_product_price: (args, env) =>
    getProductPrice(args as { sku: string }, env),
  check_inventory: (args, env) =>
    checkInventory(args as { sku: string; warehouse?: string }, env),
};

export async function dispatchToolCalls(
  toolCalls: ToolCall[],
  env: Env
): Promise<ToolResult[]> {
  return Promise.all(
    toolCalls.map(async (call) => {
      const fn = HANDLERS[call.function.name];
      if (!fn) {
        return {
          role: "tool" as const,
          tool_call_id: call.id,
          content: JSON.stringify({ error: `Unknown tool: ${call.function.name}` }),
        };
      }
      let args: Record<string, unknown>;
      try {
        args = JSON.parse(call.function.arguments);
      } catch {
        args = {};
      }
      const content = await fn(args, env);
      return { role: "tool" as const, tool_call_id: call.id, content };
    })
  );
}
```

---

## Section 3 — Worker Entry Point

```typescript
// src/index.ts
import { TOOLS, dispatchToolCalls, type ToolCall } from "./tools";

export interface Env {
  AI: Ai;
  TOOL_CACHE: KVNamespace;
}

const MODEL = "@cf/meta/llama-3.1-8b-instruct";
const MAX_TURNS = 5;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("POST only", { status: 405 });
    }

    const { userMessage } = await request.json<{ userMessage: string }>();

    const messages: Array<{
      role: string;
      content?: string;
      tool_calls?: ToolCall[];
      tool_call_id?: string;
    }> = [{ role: "user", content: userMessage }];

    let finalContent = "";

    for (let turn = 0; turn < MAX_TURNS; turn++) {
      // @ts-expect-error — Workers AI types may lag behind
      const response = await env.AI.run(MODEL, { messages, tools: TOOLS });

      const choice = (response as { response?: string; tool_calls?: ToolCall[] });

      // Model finished with a text answer
      if (choice.response) {
        finalContent = choice.response;
        break;
      }

      // Model wants to call tools
      if (!choice.tool_calls?.length) break;

      // Append the assistant turn with tool_calls
      messages.push({ role: "assistant", tool_calls: choice.tool_calls });

      // Dispatch and append results
      const results = await dispatchToolCalls(choice.tool_calls, env);
      for (const r of results) messages.push(r);
    }

    return Response.json({ answer: finalContent, turns: messages.length });
  },
};
```

---

## Anti-patterns

- **Calling tools inside the first `AI.run` response without checking `tool_calls`** — the model may answer directly; always branch on whether `tool_calls` is present before dispatching.
- **Passing raw tool results as `role: "user"`** — results must be `role: "tool"` with the matching `tool_call_id`, otherwise the model cannot correlate them.
- **Infinite loops on malformed tool arguments** — cap at `MAX_TURNS` and break on empty `tool_calls` to prevent runaway billing.
- **Skipping KV caching for stable data** — deterministic lookups like product prices are safe to cache; caching saves AI tokens and cuts p99 latency significantly.

---

## Gotchas

- `tool_call_id` must be echoed back verbatim; Llama generates UUIDs but the format is model-specific.
- `arguments` is always a JSON *string*, not an object — always `JSON.parse` before use.
- Workers AI streaming (`stream: true`) does not support tool calling; use non-streaming for agentic loops.
- KV `expirationTtl` is in seconds; set short TTLs for inventory (changes fast) and longer for pricing.

---

## Verification

```bash
# Deploy
npx wrangler deploy

# Test tool dispatch round-trip
curl -s -X POST https://ai-tool-dispatch.<account>.workers.dev \
  -H 'Content-Type: application/json' \
  -d '{"userMessage": "What is the price and stock of SKU ABC-123 in eu-west?"}' | jq .

# Confirm KV cache hit on second identical request
curl -s -X POST https://ai-tool-dispatch.<account>.workers.dev \
  -H 'Content-Type: application/json' \
  -d '{"userMessage": "What is the price and stock of SKU ABC-123 in eu-west?"}' | jq .turns
# Should be lower turn count on cache hit paths
```

---

## Related

- `workers-ai-streaming-text-readable-stream.md`
- `workers-ai-rag-chunking-vectorize.md`

---

## Sources

- Cloudflare Workers AI tool calling docs — https://developers.cloudflare.com/workers-ai/function-calling/
- Llama 3.1 model card on Cloudflare — https://developers.cloudflare.com/workers-ai/models/llama-3.1-8b-instruct/
