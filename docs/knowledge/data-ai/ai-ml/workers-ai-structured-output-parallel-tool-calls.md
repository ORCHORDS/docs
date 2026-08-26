# Workers AI Structured Output with Parallel Tool Calls

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
Agentic Workers need to extract structured data (typed JSON) from an LLM response *and* invoke multiple tools in a single model round-trip — for example, querying a database, calling an external API, and writing to R2 simultaneously based on a single user request. Sequential tool calls add latency; parallel execution with schema-validated output reduces round-trips and keeps types safe.

## Context
Workers AI's function-calling models (e.g. `@cf/meta/llama-3.3-70b-instruct-fp8-fast`) support OpenAI-compatible `tools` arrays. When the model returns `tool_calls` alongside or instead of `content`, a Workers dispatcher can fire all tool calls with `Promise.all`, collect results, and feed them back as `tool` role messages in a second completion request. Combining this with a JSON schema in the final completion forces structured extraction into a typed response. The entire pattern runs within a single Worker with Durable Objects for session state.

## Tool Registry

```typescript
// tool-registry.ts
import type { R2Bucket, D1Database } from '@cloudflare/workers-types';

export interface ToolDefinition {
  type: 'function';
  function: {
    name: string;
    description: string;
    parameters: {
      type: 'object';
      properties: Record<string, unknown>;
      required: string[];
    };
  };
}

export const TOOLS: ToolDefinition[] = [
  {
    type: 'function',
    function: {
      name: 'lookup_customer',
      description: 'Fetch customer details from the database by email or ID',
      parameters: {
        type: 'object',
        properties: {
          identifier: { type: 'string', description: 'Customer email or UUID' },
          by: { type: 'string', enum: ['email', 'id'] },
        },
        required: ['identifier', 'by'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_order_history',
      description: 'Return the last N orders for a customer ID',
      parameters: {
        type: 'object',
        properties: {
          customerId: { type: 'string' },
          limit: { type: 'number', default: 5 },
        },
        required: ['customerId'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'fetch_product_details',
      description: 'Return product name, price, and stock for a product SKU',
      parameters: {
        type: 'object',
        properties: {
          sku: { type: 'string' },
        },
        required: ['sku'],
      },
    },
  },
];

export interface ToolEnv {
  DB: D1Database;
  DOCS: R2Bucket;
}

export async function dispatchTool(
  env: ToolEnv,
  name: string,
  args: Record<string, unknown>,
): Promise<unknown> {
  switch (name) {
    case 'lookup_customer': {
      const { identifier, by } = args as { identifier: string; by: 'email' | 'id' };
      const col = by === 'email' ? 'email' : 'id';
      const row = await env.DB
        .prepare(`SELECT id, name, email, tier FROM customers WHERE ${col} = ?`)
        .bind(identifier)
        .first();
      return row ?? { error: 'Customer not found' };
    }
    case 'get_order_history': {
      const { customerId, limit = 5 } = args as { customerId: string; limit?: number };
      const { results } = await env.DB
        .prepare('SELECT order_id, total, status, created_at FROM orders WHERE customer_id = ? ORDER BY created_at DESC LIMIT ?')
        .bind(customerId, limit)
        .all();
      return results;
    }
    case 'fetch_product_details': {
      const { sku } = args as { sku: string };
      const row = await env.DB
        .prepare('SELECT name, price_cents, stock_count FROM products WHERE sku = ?')
        .bind(sku)
        .first();
      return row ?? { error: 'Product not found' };
    }
    default:
      return { error: `Unknown tool: ${name}` };
  }
}
```

## Parallel Tool Call Execution

```typescript
// parallel-agent.ts
import type { Ai } from '@cloudflare/workers-types';
import { TOOLS, dispatchTool, type ToolEnv } from './tool-registry';

interface Env extends ToolEnv {
  AI: Ai;
}

interface ChatMessage {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string | null;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
  name?: string;
}

interface ToolCall {
  id: string;
  type: 'function';
  function: { name: string; arguments: string };
}

/** Final structured response schema */
interface AgentResponse {
  summary: string;
  customer: { id: string; name: string; tier: string } | null;
  recentOrders: Array<{ orderId: string; total: number; status: string }>;
  recommendations: string[];
  actionRequired: boolean;
}

const SYSTEM_PROMPT = `You are a customer success assistant. Use the available tools to gather information.
After all tool calls complete, synthesise a structured JSON response matching the schema exactly.`;

const RESPONSE_SCHEMA = {
  type: 'object',
  properties: {
    summary: { type: 'string' },
    customer: {
      oneOf: [
        {
          type: 'object',
          properties: {
            id: { type: 'string' },
            name: { type: 'string' },
            tier: { type: 'string' },
          },
          required: ['id', 'name', 'tier'],
        },
        { type: 'null' },
      ],
    },
    recentOrders: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          orderId: { type: 'string' },
          total: { type: 'number' },
          status: { type: 'string' },
        },
        required: ['orderId', 'total', 'status'],
      },
    },
    recommendations: { type: 'array', items: { type: 'string' } },
    actionRequired: { type: 'boolean' },
  },
  required: ['summary', 'customer', 'recentOrders', 'recommendations', 'actionRequired'],
};

export async function runParallelAgent(
  env: Env,
  userQuery: string,
  maxRounds = 3,
): Promise<AgentResponse> {
  const messages: ChatMessage[] = [
    { role: 'system', content: SYSTEM_PROMPT },
    { role: 'user', content: userQuery },
  ];

  for (let round = 0; round < maxRounds; round++) {
    const completion = await env.AI.run('@cf/meta/llama-3.3-70b-instruct-fp8-fast', {
      messages,
      tools: TOOLS,
      // Only enforce JSON schema on the final round (no more tool_calls expected)
      ...(round === maxRounds - 1
        ? { response_format: { type: 'json_schema', json_schema: { schema: RESPONSE_SCHEMA } } }
        : {}),
    } as Parameters<typeof env.AI.run>[1]);

    const response = completion as {
      response?: string;
      tool_calls?: ToolCall[];
    };

    // No tool calls — model is done; parse and return
    if (!response.tool_calls || response.tool_calls.length === 0) {
      const raw = response.response ?? '{}';
      try {
        return JSON.parse(raw) as AgentResponse;
      } catch {
        throw new Error(`Invalid JSON from model: ${raw.slice(0, 200)}`);
      }
    }

    // Append assistant message with tool_calls
    messages.push({
      role: 'assistant',
      content: null,
      tool_calls: response.tool_calls,
    });

    // Execute all tool calls in parallel
    const toolResults = await Promise.all(
      response.tool_calls.map(async tc => {
        let args: Record<string, unknown>;
        try {
          args = JSON.parse(tc.function.arguments);
        } catch {
          args = {};
        }
        const result = await dispatchTool(env, tc.function.name, args);
        return { toolCallId: tc.id, name: tc.function.name, result };
      }),
    );

    // Append tool results as individual tool messages
    for (const { toolCallId, name, result } of toolResults) {
      messages.push({
        role: 'tool',
        tool_call_id: toolCallId,
        name,
        content: JSON.stringify(result),
      });
    }
  }

  throw new Error('Max tool call rounds exceeded');
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { query } = (await req.json()) as { query: string };
    const result = await runParallelAgent(env, query);
    return Response.json(result);
  },
} satisfies ExportedHandler<Env>;
```

## Schema Validation with Zod

```typescript
// validate-response.ts
import { z } from 'zod';

const AgentResponseSchema = z.object({
  summary: z.string().min(1),
  customer: z
    .object({ id: z.string(), name: z.string(), tier: z.string() })
    .nullable(),
  recentOrders: z.array(
    z.object({
      orderId: z.string(),
      total: z.number(),
      status: z.string(),
    }),
  ),
  recommendations: z.array(z.string()),
  actionRequired: z.boolean(),
});

export function validateAgentResponse(raw: unknown) {
  const result = AgentResponseSchema.safeParse(raw);
  if (!result.success) {
    throw new Error(`Schema validation failed: ${result.error.message}`);
  }
  return result.data;
}
```

## Observability: Logging Tool Call Parallelism

```typescript
// telemetry.ts
export interface ToolCallTelemetry {
  round: number;
  toolNames: string[];
  parallelCount: number;
  durationMs: number;
}

export function logToolRound(
  analytics: AnalyticsEngineDataset,
  telemetry: ToolCallTelemetry,
): void {
  analytics.writeDataPoint({
    blobs: [JSON.stringify(telemetry.toolNames)],
    doubles: [telemetry.parallelCount, telemetry.durationMs, telemetry.round],
    indexes: [String(telemetry.round)],
  });
}
```

## Anti-patterns

- **Serialising tool calls with `await` in a for-loop** — defeats the latency benefit; always use `Promise.all` over the `tool_calls` array.
- **Enforcing JSON schema on every round** — the model cannot return `tool_calls` when constrained to a JSON schema; only apply the schema on the final round or when `tool_calls` is empty.
- **Not validating the final JSON against Zod** — Workers AI may produce syntactically valid but semantically wrong JSON; always validate against your schema before returning to callers.
- **Passing the full message history to the model on every round without trimming** — long tool results accumulate quickly; truncate large tool result strings to 2 KB each before re-appending.
- **Unlimited `maxRounds`** — a buggy tool can cause the model to call tools indefinitely; cap rounds at 3–5 and throw a typed error on exhaustion.

## Gotchas

- Workers AI `tool_calls` field is present only when the model decides to call tools; check for `undefined` or empty array before attempting dispatch.
- `tc.function.arguments` is a *string* containing JSON, not a parsed object — always `JSON.parse()` and catch parse errors.
- Parallel D1 queries in `Promise.all` count against D1's per-request concurrency limit (50 statements per request as of mid-2026); batch independent reads into a single `D1Database.batch()` call instead.
- The `response_format: json_schema` parameter name and shape vary by Workers AI model; test with your target model in `wrangler dev` before deploying.
- Tool result messages must use `role: 'tool'` and include the matching `tool_call_id` from the `tool_calls` array; mismatched IDs cause the model to ignore the result.

## Verification

```bash
# 1. Start wrangler dev
wrangler dev

# 2. Send a multi-tool query
curl -X POST http://localhost:8787 \
  -H 'Content-Type: application/json' \
  -d '{"query":"Look up customer john@example.com, get their last 3 orders, and fetch details for SKU PROD-42"}'

# Expected: JSON with customer, recentOrders, recommendations, actionRequired
# Verify all 3 tool calls fired in the same round (check logs for parallel dispatches)

# 3. Validate schema compliance
node -e "
  const r = require('./dist/validate-response');
  const data = {summary:'ok',customer:null,recentOrders:[],recommendations:[],actionRequired:false};
  console.log(r.validateAgentResponse(data));
"
```

## Related

- `workers-ai-function-calling-agentic-patterns.md`
- `llm-function-calling-tool-use-patterns.md`
- `llm-structured-output-vs-function-calling.md`
- `workers-ai-json-schema-constrained-generation.md`
- `llm-structured-extraction-zod-workers.md`

## Sources

- https://developers.cloudflare.com/workers-ai/function-calling/
- https://platform.openai.com/docs/guides/function-calling
- https://developers.cloudflare.com/d1/
