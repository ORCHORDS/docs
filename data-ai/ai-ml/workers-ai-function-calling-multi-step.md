# Multi-Step Function Calling with Workers AI and D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want an LLM inside a Cloudflare Worker to answer questions that require live data — e.g. "how many orders did customer 42 place last month?". Function calling lets the model declare intent (`tool_calls`), your Worker executes a real D1 query, then feeds the result back for a final answer. This pattern avoids hallucinated data and keeps business logic in your code.

## Context

- Runtime: Cloudflare Workers (ES modules)
- Bindings: `AI` (Workers AI), `DB` (D1 database)
- Model: `@cf/meta/llama-3.1-8b-instruct` (tool-use capable)
- Pattern: user message → model emits `tool_calls` → Worker runs D1 → second model call → final text answer

---

## Section 1: Wrangler Configuration

```toml
# wrangler.toml
name = "ai-function-calling"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[ai]
binding = "AI"

[[d1_databases]]
binding = "DB"
database_name = "orders_db"
database_id = "<your-d1-database-id>"
```

## Section 2: Tool Schema Definition

Workers AI expects tools in OpenAI-compatible format.

```typescript
// src/tools.ts
export const TOOLS = [
  {
    type: 'function' as const,
    function: {
      name: 'get_order_count',
      description: 'Returns the number of orders placed by a customer in a given month.',
      parameters: {
        type: 'object',
        properties: {
          customer_id: {
            type: 'integer',
            description: 'The numeric customer ID.',
          },
          year: {
            type: 'integer',
            description: 'Calendar year, e.g. 2026.',
          },
          month: {
            type: 'integer',
            description: 'Calendar month 1–12.',
          },
        },
        required: ['customer_id', 'year', 'month'],
      },
    },
  },
  {
    type: 'function' as const,
    function: {
      name: 'get_customer_info',
      description: 'Returns name and email for a customer by ID.',
      parameters: {
        type: 'object',
        properties: {
          customer_id: {
            type: 'integer',
            description: 'The numeric customer ID.',
          },
        },
        required: ['customer_id'],
      },
    },
  },
];
```

## Section 3: Tool Execution Against D1

```typescript
// src/tool-executor.ts
import { D1Database } from '@cloudflare/workers-types';

export interface ToolCall {
  id: string;
  type: 'function';
  function: { name: string; arguments: string };
}

export async function executeToolCall(
  toolCall: ToolCall,
  db: D1Database
): Promise<string> {
  let args: Record<string, unknown>;
  try {
    args = JSON.parse(toolCall.function.arguments);
  } catch {
    return JSON.stringify({ error: 'Invalid tool arguments JSON' });
  }

  switch (toolCall.function.name) {
    case 'get_order_count': {
      const { customer_id, year, month } = args as {
        customer_id: number;
        year: number;
        month: number;
      };
      const result = await db
        .prepare(
          `SELECT COUNT(*) as count FROM orders
           WHERE customer_id = ?
             AND strftime('%Y', created_at) = ?
             AND strftime('%m', created_at) = ?`
        )
        .bind(
          customer_id,
          String(year),
          String(month).padStart(2, '0')
        )
        .first<{ count: number }>();
      return JSON.stringify({ order_count: result?.count ?? 0 });
    }

    case 'get_customer_info': {
      const { customer_id } = args as { customer_id: number };
      const row = await db
        .prepare('SELECT name, email FROM customers WHERE id = ?')
        .bind(customer_id)
        .first<{ name: string; email: string }>();
      if (!row) return JSON.stringify({ error: 'Customer not found' });
      return JSON.stringify(row);
    }

    default:
      return JSON.stringify({ error: `Unknown tool: ${toolCall.function.name}` });
  }
}
```

## Section 4: Multi-Step Agent Loop

```typescript
// src/agent.ts
import { Ai, D1Database } from '@cloudflare/workers-types';
import { TOOLS } from './tools';
import { executeToolCall, ToolCall } from './tool-executor';

type Message = { role: 'system' | 'user' | 'assistant' | 'tool'; content: string; tool_call_id?: string };

export async function runAgent(
  ai: Ai,
  db: D1Database,
  userQuery: string,
  maxSteps = 5
): Promise<string> {
  const messages: Message[] = [
    {
      role: 'system',
      content:
        'You are a helpful customer support assistant with access to order and customer data. ' +
        'Use the provided tools to look up real data before answering. Never guess IDs or counts.',
    },
    { role: 'user', content: userQuery },
  ];

  for (let step = 0; step < maxSteps; step++) {
    const response = await (ai as any).run('@cf/meta/llama-3.1-8b-instruct', {
      messages,
      tools: TOOLS,
      max_tokens: 1024,
      temperature: 0.2,
    });

    const toolCalls: ToolCall[] | undefined = response.tool_calls;

    // No tool calls → model is done, return final answer
    if (!toolCalls || toolCalls.length === 0) {
      return (response as { response?: string }).response ?? '[no response]';
    }

    // Append assistant message with tool_calls
    messages.push({
      role: 'assistant',
      content: JSON.stringify({ tool_calls: toolCalls }),
    });

    // Execute each tool and append tool result messages
    for (const toolCall of toolCalls) {
      const result = await executeToolCall(toolCall, db);
      messages.push({
        role: 'tool',
        content: result,
        tool_call_id: toolCall.id,
      });
    }
  }

  throw new Error('[agent] exceeded maxSteps without a final answer');
}
```

## Section 5: Worker Entry Point

```typescript
// src/index.ts
import { runAgent } from './agent';

export interface Env {
  AI: Ai;
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('POST { "query": "..." }', { status: 405 });
    }
    const { query } = await request.json<{ query: string }>();
    if (!query?.trim()) return new Response('Missing query', { status: 400 });

    try {
      const answer = await runAgent(env.AI, env.DB, query);
      return Response.json({ answer });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      return Response.json({ error: msg }, { status: 500 });
    }
  },
};
```

## Anti-patterns

- Do NOT let the model call tools with unvalidated arguments directly against D1 — always parse and type-check `arguments` before binding.
- Do NOT allow unbounded `maxSteps` — a rogue or confused model can loop indefinitely consuming AI quota.
- Do NOT return raw D1 row objects to the model when they contain PII or large blobs; project only the fields the model needs.
- Do NOT use `role: 'function'` — Workers AI follows the OpenAI v2 spec which uses `role: 'tool'` with `tool_call_id`.
- Do NOT skip appending the assistant message with `tool_calls` before appending `tool` messages — the conversation history must stay coherent.

## Gotchas

- `tool_calls` in the response may be `undefined` (not an empty array) when the model answers directly — always check for `undefined`.
- Llama 3.1 8B may emit malformed JSON in `arguments`; wrap `JSON.parse` in try/catch and return an error string to the model.
- D1's `strftime` uses SQLite semantics — months are zero-padded (`'01'` not `'1'`).
- Workers AI's `tools` parameter naming may differ from pure OpenAI; test with `wrangler dev --remote` not just locally.
- Each model round-trip adds latency; keep tool result payloads small (< 1 KB) to avoid bloating context.

## Verification

```bash
# Create D1 schema
npx wrangler d1 execute orders_db --remote --command "
  CREATE TABLE IF NOT EXISTS customers (id INTEGER PRIMARY KEY, name TEXT, email TEXT);
  CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, customer_id INTEGER, created_at TEXT);
  INSERT INTO customers VALUES (42, 'Alice Smith', 'alice@example.com');
  INSERT INTO orders VALUES (1, 42, '2026-07-15T10:00:00Z');
  INSERT INTO orders VALUES (2, 42, '2026-07-22T14:30:00Z');
"

# Deploy and test
npx wrangler deploy
curl -X POST https://ai-function-calling.<subdomain>.workers.dev \
  -H 'Content-Type: application/json' \
  -d '{"query": "How many orders did customer 42 place in July 2026?"}'
# Expected: { answer: "Customer 42 placed 2 orders in July 2026." }
```

## Related

- `documentation/categories/ai-ml/workers-ai-json-mode-structured-output.md`
- `documentation/categories/ai-ml/workers-ai-batch-inference-queues.md`
- `documentation/categories/ai-ml/workers-ai-rag-reranking-vectorize.md`

## Sources

- https://developers.cloudflare.com/workers-ai/function-calling/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers-ai/models/llama-3.1-8b-instruct/
