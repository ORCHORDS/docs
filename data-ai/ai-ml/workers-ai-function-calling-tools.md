# Tool/Function Calling with Workers AI Models

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You need an LLM running on Workers AI to take actions — look up a database record, call an external API, run a calculation — rather than just producing text. Without tool calling, you must manually parse the model output and re-prompt. Tool calling gives the model a structured way to request actions and receive results.

## Context

Workers AI models that support tool use (e.g. `@cf/meta/llama-3.1-8b-instruct`, `@cf/qwen/qwen1.5-14b-chat-awq`) accept a `tools` array in the chat-completion request. The model may respond with a `tool_calls` array instead of a text response. Your Worker executes the requested tool, appends the result as a `tool` role message, and re-sends the conversation until the model produces a final text response.

The loop must have a hard iteration cap to prevent runaway token consumption.

## Solution

### 1. Tool definitions

```typescript
// src/tools/definitions.ts
import type { AiTextGenerationToolInput } from '@cloudflare/workers-types';

export const tools: AiTextGenerationToolInput[] = [
  {
    name: 'get_order_status',
    description: 'Returns the current status and estimated delivery date for a given order ID.',
    parameters: {
      type: 'object',
      properties: {
        order_id: {
          type: 'string',
          description: 'The alphanumeric order identifier, e.g. ORD-12345',
        },
      },
      required: ['order_id'],
    },
  },
  {
    name: 'list_products',
    description: 'Returns a list of products matching a search query.',
    parameters: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Product search keywords' },
        max_results: {
          type: 'number',
          description: 'Maximum number of results to return (default 5)',
        },
      },
      required: ['query'],
    },
  },
  {
    name: 'calculate_shipping',
    description: 'Calculates shipping cost between two ZIP codes for a given weight.',
    parameters: {
      type: 'object',
      properties: {
        from_zip: { type: 'string' },
        to_zip: { type: 'string' },
        weight_kg: { type: 'number' },
      },
      required: ['from_zip', 'to_zip', 'weight_kg'],
    },
  },
];
```

### 2. Tool execution dispatch

```typescript
// src/tools/executor.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface ToolExecutorEnv {
  DB: D1Database;
}

type ToolArgs = Record<string, unknown>;

export async function executeTool(
  name: string,
  args: ToolArgs,
  env: ToolExecutorEnv,
): Promise<string> {
  switch (name) {
    case 'get_order_status':
      return getOrderStatus(String(args.order_id), env.DB);
    case 'list_products':
      return listProducts(String(args.query), Number(args.max_results ?? 5), env.DB);
    case 'calculate_shipping':
      return calculateShipping(
        String(args.from_zip),
        String(args.to_zip),
        Number(args.weight_kg),
      );
    default:
      return JSON.stringify({ error: `Unknown tool: ${name}` });
  }
}

async function getOrderStatus(orderId: string, db: D1Database): Promise<string> {
  const row = await db
    .prepare('SELECT status, estimated_delivery FROM orders WHERE id = ?')
    .bind(orderId)
    .first<{ status: string; estimated_delivery: string }>();

  if (!row) return JSON.stringify({ error: 'Order not found' });
  return JSON.stringify(row);
}

async function listProducts(query: string, maxResults: number, db: D1Database): Promise<string> {
  const { results } = await db
    .prepare(
      `SELECT id, name, price FROM products
       WHERE name LIKE ? LIMIT ?`,
    )
    .bind(`%${query}%`, Math.min(maxResults, 20))
    .all<{ id: string; name: string; price: number }>();

  return JSON.stringify(results);
}

function calculateShipping(fromZip: string, toZip: string, weightKg: number): string {
  // Simplified flat-rate calculation
  const baseCost = 5.99;
  const perKg = 1.50;
  const cost = baseCost + weightKg * perKg;
  return JSON.stringify({ from: fromZip, to: toZip, weight_kg: weightKg, cost_usd: cost });
}
```

### 3. Multi-turn conversation loop

```typescript
// src/lib/agent.ts
import type { Ai } from '@cloudflare/workers-types';
import { tools } from '../tools/definitions';
import { executeTool, type ToolExecutorEnv } from '../tools/executor';

const MAX_ITERATIONS = 6; // hard cap on tool calls per conversation

type Message = {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string;
  tool_call_id?: string;
  name?: string;
};

interface ToolCall {
  id: string;
  name: string;
  arguments: string; // JSON string
}

export async function runAgent(
  ai: Ai,
  env: ToolExecutorEnv,
  userMessage: string,
): Promise<string> {
  const messages: Message[] = [
    {
      role: 'system',
      content:
        'You are a helpful e-commerce assistant. Use the provided tools to look up real data. ' +
        'Always call a tool when you need specific information rather than guessing.',
    },
    { role: 'user', content: userMessage },
  ];

  for (let iteration = 0; iteration < MAX_ITERATIONS; iteration++) {
    const response = await ai.run('@cf/meta/llama-3.1-8b-instruct', {
      messages,
      tools,
      stream: false,
    } as Parameters<typeof ai.run>[1]);

    // Cast to access tool_calls
    const res = response as {
      response?: string;
      tool_calls?: ToolCall[];
    };

    // No tool calls — model produced a final text answer
    if (!res.tool_calls || res.tool_calls.length === 0) {
      return res.response ?? '';
    }

    // Append the assistant turn with tool_calls
    messages.push({
      role: 'assistant',
      content: res.response ?? '',
    });

    // Execute each requested tool and append results
    for (const toolCall of res.tool_calls) {
      let args: Record<string, unknown>;
      try {
        args = JSON.parse(toolCall.arguments);
      } catch {
        args = {};
      }

      const result = await executeTool(toolCall.name, args, env);

      messages.push({
        role: 'tool',
        tool_call_id: toolCall.id,
        name: toolCall.name,
        content: result,
      });
    }
  }

  // Safety: if max iterations hit, ask for a plain answer without tools
  messages.push({
    role: 'user',
    content: 'Please summarise what you found and give a final answer now.',
  });

  const fallback = await ai.run('@cf/meta/llama-3.1-8b-instruct', {
    messages,
    stream: false,
  } as Parameters<typeof ai.run>[1]);

  return (fallback as { response?: string }).response ?? 'Max iterations reached.';
}
```

### 4. Worker entry point

```typescript
// src/index.ts
import { runAgent } from './lib/agent';

export interface Env {
  AI: Ai;
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('POST only', { status: 405 });

    const { message } = await request.json<{ message: string }>();
    if (!message?.trim()) return new Response('Empty message', { status: 400 });

    const answer = await runAgent(env.AI, { DB: env.DB }, message);
    return Response.json({ answer });
  },
};
```

### 5. wrangler.jsonc

```jsonc
{
  "name": "agent-worker",
  "main": "src/index.ts",
  "compatibility_date": "2025-09-01",
  "ai": { "binding": "AI" },
  "d1_databases": [
    { "binding": "DB", "database_name": "ecommerce", "database_id": "<id>" }
  ]
}
```

## Implementation Details

### Tool argument parsing

Always wrap `JSON.parse(toolCall.arguments)` in try/catch. Some models occasionally produce malformed JSON for tool arguments; returning an error string as the tool result allows the model to recover gracefully on the next turn.

### Tool call deduplication

If the model calls the same tool with identical arguments twice in a row, you are likely in a loop caused by a tool returning an unexpected result. Track recent `(name, args)` pairs and short-circuit if a duplicate is detected.

### Conversation token budget

Each iteration appends messages; the conversation can grow past the model context window. Summarise earlier tool results if the message list exceeds ~12 messages.

### Safety limits recap

| Limit | Value | Reason |
|---|---|---|
| `MAX_ITERATIONS` | 6 | Prevents infinite loops |
| DB query `LIMIT` | 20 | Caps tool result size |
| Tool result max length | 2000 chars | Keeps context window healthy |

## Anti-patterns

- **Unlimited iteration loops**: without `MAX_ITERATIONS`, a confused model can call tools indefinitely.
- **Executing tool calls from untrusted model output without validation**: always validate parsed arguments against expected types before passing to database or network calls.
- **Giving the model too many tools**: more than 10 tools significantly confuses smaller models; keep the tool list minimal and domain-specific.
- **Returning raw database rows with sensitive columns**: scrub passwords, PII, and internal IDs before returning tool results to the model.
- **Using stream: true with tool calls**: streaming responses require special handling of partial chunks; use `stream: false` for agentic loops.

## Gotchas

- Not all Workers AI models support `tools`; check the model card. Unsupported models silently ignore the `tools` array and produce text output.
- The `tool` role message must include the `tool_call_id` matching the request; omitting it causes some models to loop asking for the result again.
- Workers AI has a per-Worker CPU time limit (typically 30s on free, 5min on paid); long agentic loops may hit it.
- Tool argument `arguments` is a JSON *string*, not a parsed object — always `JSON.parse` before use.

## Verification

```bash
curl -X POST https://agent-worker.<account>.workers.dev \
  -H 'Content-Type: application/json' \
  -d '{"message": "What is the status of order ORD-99999?"}'
# Model calls get_order_status, receives result, replies:
# => {"answer": "Order ORD-99999 is currently In Transit, estimated delivery 2026-08-27."}

curl -X POST https://agent-worker.<account>.workers.dev \
  -H 'Content-Type: application/json' \
  -d '{"message": "How much does it cost to ship a 2kg package from 10001 to 90001?"}'
# Model calls calculate_shipping
# => {"answer": "Shipping a 2 kg package from ZIP 10001 to 90001 costs $8.99."}
```

## Related

- `workers-ai-structured-output-json.md` — structured output without tool calling
- `workers-ai-content-moderation-gateway.md` — gating tool calls through safety checks
- Cloudflare Workers AI tool use docs: https://developers.cloudflare.com/workers-ai/function-calling/

## Sources

- Cloudflare Workers AI — Function Calling: https://developers.cloudflare.com/workers-ai/function-calling/
- Llama 3.1 tool use documentation (Meta)
- OpenAI tool calling specification (reference for message schema)
