# Workers AI Function Calling / Tool Use

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need an LLM to take actions — query a database, call an external API, compute a value — rather than just return text. Workers AI supports a function-calling / tool-use protocol identical to OpenAI's: the model emits `tool_call` objects instead of prose, your Worker executes the real function, and you feed the result back for a final answer. This article covers the full loop: schema definition, response parsing, parallel calls, error propagation, and streaming.

---

## Context

Workers AI (`@cf/meta/llama-3.1-8b-instruct`, `@cf/mistral/mistral-7b-instruct-v0.2-lora`, and compatible models) accepts an `tools` array alongside the `messages` array. When the model decides a tool is needed it returns a `finish_reason` of `tool_calls` and populates `message.tool_calls[]`. Your code must dispatch those calls, collect results, append both the assistant message and the tool result messages, and call the model again. The pattern is identical to OpenAI tool use so existing prompt engineering transfers directly.

---

## Solution

```typescript
// src/index.ts
import { Ai } from '@cloudflare/ai';

export interface Env {
  AI: Ai;
  DB: D1Database;
}

// ── Tool schemas sent to the model ──────────────────────────────────────────

const TOOLS: AiTextGenerationToolInput[] = [
  {
    type: 'function',
    function: {
      name: 'get_product',
      description: 'Retrieve a product record by SKU from the catalog.',
      parameters: {
        type: 'object',
        properties: {
          sku: { type: 'string', description: 'Product SKU, e.g. "ORD-1234"' },
        },
        required: ['sku'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'list_orders',
      description: 'List recent orders for a customer email address.',
      parameters: {
        type: 'object',
        properties: {
          email: { type: 'string', description: 'Customer email' },
          limit: { type: 'number', description: 'Max results (default 5)' },
        },
        required: ['email'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'calculate_shipping',
      description: 'Estimate shipping cost for a given weight (kg) and destination country.',
      parameters: {
        type: 'object',
        properties: {
          weight_kg: { type: 'number' },
          country_code: { type: 'string', description: 'ISO 3166-1 alpha-2' },
        },
        required: ['weight_kg', 'country_code'],
      },
    },
  },
];

// ── Local function implementations ───────────────────────────────────────────

type ToolArgs = Record<string, unknown>;
type ToolResult = Record<string, unknown> | string;

async function get_product(args: ToolArgs, env: Env): Promise<ToolResult> {
  const { sku } = args as { sku: string };
  const row = await env.DB
    .prepare('SELECT * FROM products WHERE sku = ? LIMIT 1')
    .bind(sku)
    .first<Record<string, unknown>>();
  if (!row) return { error: `No product found for SKU ${sku}` };
  return row;
}

async function list_orders(args: ToolArgs, env: Env): Promise<ToolResult> {
  const { email, limit = 5 } = args as { email: string; limit?: number };
  const { results } = await env.DB
    .prepare(
      'SELECT id, created_at, status, total FROM orders WHERE customer_email = ? ORDER BY created_at DESC LIMIT ?'
    )
    .bind(email, limit)
    .all<Record<string, unknown>>();
  return { orders: results };
}

async function calculate_shipping(
  args: ToolArgs,
  _env: Env
): Promise<ToolResult> {
  const { weight_kg, country_code } = args as {
    weight_kg: number;
    country_code: string;
  };
  // Simplified rate table — replace with real carrier API call.
  const baseRate: Record<string, number> = { US: 5, GB: 9, DE: 11, AU: 18 };
  const rate = baseRate[country_code.toUpperCase()] ?? 20;
  const cost = (rate + weight_kg * 2.5).toFixed(2);
  return { estimated_usd: cost, currency: 'USD' };
}

// ── Tool dispatcher ───────────────────────────────────────────────────────────

async function dispatchTool(
  name: string,
  args: ToolArgs,
  env: Env
): Promise<ToolResult> {
  switch (name) {
    case 'get_product':        return get_product(args, env);
    case 'list_orders':        return list_orders(args, env);
    case 'calculate_shipping': return calculate_shipping(args, env);
    default:
      return { error: `Unknown tool: ${name}` };
  }
}

// ── Agentic loop ─────────────────────────────────────────────────────────────

const MAX_ITERATIONS = 6; // guard against infinite tool-call loops

async function runAgentLoop(
  userMessage: string,
  env: Env
): Promise<string> {
  const messages: RoleScopedChatInput[] = [
    {
      role: 'system',
      content:
        'You are a helpful e-commerce assistant. Use the provided tools to answer questions accurately. Do not guess — always call a tool to retrieve real data.',
    },
    { role: 'user', content: userMessage },
  ];

  for (let i = 0; i < MAX_ITERATIONS; i++) {
    const response = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
      messages,
      tools: TOOLS,
      max_tokens: 1024,
    });

    // If the model produced a final answer, return it.
    if (response.response) {
      return response.response;
    }

    // Handle tool calls (may be parallel).
    const toolCalls = response.tool_calls;
    if (!toolCalls || toolCalls.length === 0) {
      // Model returned neither text nor tool calls — surface the raw output.
      return JSON.stringify(response);
    }

    // Append the assistant message that contains the tool_calls array.
    messages.push({
      role: 'assistant',
      content: response.response ?? '',   // may be empty for pure tool-call turns
      // @ts-expect-error: tool_calls is not yet in the type definitions
      tool_calls: toolCalls,
    });

    // Execute all tool calls in parallel.
    const toolResults = await Promise.allSettled(
      toolCalls.map(async (tc) => {
        let args: ToolArgs = {};
        try {
          args =
            typeof tc.function.arguments === 'string'
              ? JSON.parse(tc.function.arguments)
              : tc.function.arguments;
        } catch {
          args = {};
        }

        let result: ToolResult;
        try {
          result = await dispatchTool(tc.function.name, args, env);
        } catch (err) {
          // Propagate execution errors back to the model as a structured message.
          result = {
            error: err instanceof Error ? err.message : String(err),
          };
        }

        return { id: tc.id, name: tc.function.name, result };
      })
    );

    // Append one tool result message per call.
    for (const settled of toolResults) {
      if (settled.status === 'fulfilled') {
        const { id, result } = settled.value;
        messages.push({
          role: 'tool',
          // @ts-expect-error: tool_call_id not yet in type definitions
          tool_call_id: id,
          content: JSON.stringify(result),
        });
      } else {
        messages.push({
          role: 'tool',
          content: JSON.stringify({ error: settled.reason }),
        });
      }
    }
  }

  return 'Agent loop exceeded maximum iterations without a final answer.';
}

// ── Streaming variant ────────────────────────────────────────────────────────
// Workers AI streaming returns an EventSource (SSE) stream.
// Tool calls cannot be streamed mid-flight; only the final answer is streamed.

async function streamFinalAnswer(
  messages: RoleScopedChatInput[],
  env: Env
): Promise<ReadableStream> {
  const stream = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
    messages,
    tools: TOOLS,
    stream: true,
  });
  // Cast: Workers AI returns a ReadableStream when stream:true.
  return stream as unknown as ReadableStream;
}

// ── Request handler ───────────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405 });
    }

    const { message, stream = false } = await request.json<{
      message: string;
      stream?: boolean;
    }>();

    if (!message) {
      return Response.json({ error: 'message is required' }, { status: 400 });
    }

    if (stream) {
      // Streaming is only meaningful for the final prose answer.
      // Run the agentic loop first (non-streaming), then stream the summary.
      const agentResult = await runAgentLoop(message, env);
      const finalMessages: RoleScopedChatInput[] = [
        { role: 'user', content: message },
        { role: 'assistant', content: agentResult },
        { role: 'user', content: 'Please summarize your findings concisely.' },
      ];
      const readable = await streamFinalAnswer(finalMessages, env);
      return new Response(readable, {
        headers: { 'Content-Type': 'text/event-stream' },
      });
    }

    const answer = await runAgentLoop(message, env);
    return Response.json({ answer });
  },
};
```

---

## Implementation Details

**Tool schema**: `parameters` must be a valid JSON Schema object. Use `required` to tell the model which arguments it must supply. Omit optional fields from `required` but describe defaults in the `description` string.

**Parallel tool calls**: When `tool_calls.length > 1`, `Promise.allSettled` fans the calls out concurrently. The model may emit two or three calls in a single turn (e.g. fetch product + fetch shipping simultaneously). Always append one `role: "tool"` message per call — the `tool_call_id` links result to call.

**Message ordering**: The conversation array must follow the pattern `[system, user, assistant(tool_calls), tool, tool, ..., assistant(text)]`. Any violation causes the model to ignore tool results or produce garbage.

**Error propagation**: Returning `{ error: "..." }` as a tool result lets the model acknowledge the failure and either retry with corrected arguments or apologise to the user — far better than throwing and losing the conversation state.

**MAX_ITERATIONS guard**: Without a loop cap a misbehaving model can spin forever. Six iterations covers even multi-hop workflows (look up product → look up inventory → look up shipping) with headroom.

---

## Anti-patterns

- **Parsing `finish_reason` as a string**: Workers AI returns it as a field on the response object; always check `response.tool_calls` length instead of comparing strings.
- **Serialising `arguments` yourself**: Some model responses return `arguments` as an already-parsed object; always guard with `typeof === 'string'` before `JSON.parse`.
- **Appending tool results before the assistant tool_call message**: The model rejects this ordering and hallucinates results.
- **Allowing unbounded tool call loops**: Always set `MAX_ITERATIONS`.
- **Letting tool errors throw uncaught**: Wrap every dispatch in try/catch and return a structured `{ error }` object so the model can reason about failures.

---

## Gotchas

- `@cf/meta/llama-3.1-8b-instruct` supports tools; smaller models (`llama-3.2-1b`) do not — verify model capability before shipping.
- Workers AI does not yet surface `finish_reason: "tool_calls"` in the TypeScript types; use `// @ts-expect-error` or cast to `any` for `tool_calls` and `tool_call_id` fields.
- A single Workers AI invocation has a 30-second CPU timeout; multi-turn agentic loops that hit external APIs can exceed this. Use Durable Objects or Queues for long-running agents.
- Tool names must be valid identifiers (letters, digits, underscores) — spaces or hyphens cause parse errors on some model variants.

---

## Verification

```bash
# Start local dev
npx wrangler dev

# Test single-tool call
curl -s -X POST http://localhost:8787 \
  -H 'Content-Type: application/json' \
  -d '{"message": "What is the price of product SKU ORD-9999?"}' | jq .

# Test parallel tool calls
curl -s -X POST http://localhost:8787 \
  -H 'Content-Type: application/json' \
  -d '{"message": "List orders for alice@example.com and also estimate shipping for 2kg to Germany."}' | jq .

# Test error propagation
curl -s -X POST http://localhost:8787 \
  -H 'Content-Type: application/json' \
  -d '{"message": "Get product SKU DOES-NOT-EXIST"}' | jq .
```

Expect `answer` to contain prose that cites retrieved data. If `answer` is empty, inspect `response.tool_calls` raw — the model may have emitted a tool call without a final turn.

---

## Related

- `documentation/docs/policies/ai-ml/workers-ai-prompt-caching-kv.md` — cache repeated tool results
- `documentation/docs/policies/ai-ml/workers-ai-reranking-search-results.md` — rerank before passing results to tool
- Cloudflare Workers AI docs: https://developers.cloudflare.com/workers-ai/
- Workers AI model catalog: https://developers.cloudflare.com/workers-ai/models/

---

## Sources

- Cloudflare Workers AI — Function Calling guide (2025)
- OpenAI Tool Use specification (parallel tool calls section)
- `@cloudflare/ai` TypeScript types, v1.x
