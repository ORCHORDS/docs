# Workers AI Tool Calling with D1 Queries

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want an LLM to answer natural-language questions about live business data stored in a D1 database — without exposing raw SQL to the model. Defining typed tools (`getOrderStatus`, `listCampaigns`) and running a two-pass inference loop lets the model select and call the right function, receive real data, and compose a grounded final answer.

---

## Context

Cloudflare Workers AI supports OpenAI-compatible `tools` and `tool_choice` parameters on models like `@cf/meta/llama-3.3-70b-instruct-fp8-fast`. On the first inference pass the model responds with a `tool_calls` array rather than a content string, each element identifying a tool name and its arguments as JSON. The Worker executes the chosen tool against D1 synchronously, then appends a `tool` role message with the result and performs a second inference pass to get the final natural-language response. This pattern is identical to OpenAI function calling but runs entirely within the Cloudflare network with no egress.

---

## Section 1 — wrangler.toml / Schema

```toml
name = "ai-tool-calling-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[ai]
binding = "AI"

[[d1_databases]]
binding = "DB"
database_name = "ecommerce"
database_id = "YOUR_D1_DATABASE_ID"
```

```sql
-- D1 schema (run once)
CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY,
  customer_email TEXT NOT NULL,
  status TEXT NOT NULL,        -- pending | shipped | delivered | cancelled
  total_usd REAL NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS campaigns (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  channel TEXT NOT NULL,       -- email | sms | push
  status TEXT NOT NULL,        -- draft | active | paused | completed
  budget_usd REAL NOT NULL,
  spend_usd REAL NOT NULL DEFAULT 0,
  starts_at TEXT,
  ends_at TEXT
);
```

## Section 2 — Tool definitions and first inference pass

```typescript
import { Ai } from "@cloudflare/workers-types";

export interface Env {
  AI: Ai;
  DB: D1Database;
}

// ── Tool definitions (JSON Schema) ──────────────────────────────────────────
const tools = [
  {
    type: "function" as const,
    function: {
      name: "getOrderStatus",
      description:
        "Retrieve the status and total of a specific order by its ID.",
      parameters: {
        type: "object",
        properties: {
          order_id: {
            type: "string",
            description: "The order UUID to look up.",
          },
        },
        required: ["order_id"],
        additionalProperties: false,
      },
    },
  },
  {
    type: "function" as const,
    function: {
      name: "listCampaigns",
      description:
        "List marketing campaigns, optionally filtered by channel or status.",
      parameters: {
        type: "object",
        properties: {
          channel: {
            type: "string",
            enum: ["email", "sms", "push"],
            description: "Filter by channel. Omit to return all channels.",
          },
          status: {
            type: "string",
            enum: ["draft", "active", "paused", "completed"],
            description: "Filter by status. Omit to return all statuses.",
          },
          limit: {
            type: "number",
            description: "Max rows to return (default 10, max 50).",
          },
        },
        required: [],
        additionalProperties: false,
      },
    },
  },
];

type Message = {
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  tool_call_id?: string;
  tool_calls?: Array<{ id: string; type: "function"; function: { name: string; arguments: string } }>;
};

// ── Tool executor ─────────────────────────────────────────────────────────
async function executeTool(
  db: D1Database,
  name: string,
  args: Record<string, unknown>
): Promise<string> {
  if (name === "getOrderStatus") {
    const orderId = args["order_id"] as string;
    const row = await db
      .prepare("SELECT id, status, total_usd, created_at FROM orders WHERE id = ?")
      .bind(orderId)
      .first<{ id: string; status: string; total_usd: number; created_at: string }>();
    if (!row) return JSON.stringify({ error: "Order not found" });
    return JSON.stringify(row);
  }

  if (name === "listCampaigns") {
    const { channel, status, limit = 10 } = args as {
      channel?: string;
      status?: string;
      limit?: number;
    };
    const safeLimit = Math.min(Number(limit), 50);
    const conditions: string[] = [];
    const bindings: unknown[] = [];

    if (channel) { conditions.push("channel = ?"); bindings.push(channel); }
    if (status) { conditions.push("status = ?"); bindings.push(status); }

    const where = conditions.length ? `WHERE ${conditions.join(" AND ")}` : "";
    bindings.push(safeLimit);

    const rows = await db
      .prepare(`SELECT id, name, channel, status, budget_usd, spend_usd FROM campaigns ${where} LIMIT ?`)
      .bind(...bindings)
      .all();

    return JSON.stringify(rows.results);
  }

  return JSON.stringify({ error: `Unknown tool: ${name}` });
}
```

## Section 3 — Two-pass inference loop and request handler

```typescript
async function runAgentLoop(
  ai: Ai,
  db: D1Database,
  userQuery: string
): Promise<string> {
  const MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast";

  const messages: Message[] = [
    {
      role: "system",
      content:
        "You are a business intelligence assistant. Use the provided tools to look up live data before answering. Never fabricate data.",
    },
    { role: "user", content: userQuery },
  ];

  // ── Pass 1: model decides which tool to call ───────────────────────────
  const pass1 = (await ai.run(MODEL, {
    messages,
    tools,
    tool_choice: "auto",
  })) as {
    response?: string;
    tool_calls?: Array<{
      id: string;
      type: "function";
      function: { name: string; arguments: string };
    }>;
  };

  // If the model answered directly (no tool needed), return immediately
  if (!pass1.tool_calls || pass1.tool_calls.length === 0) {
    return pass1.response ?? "No response from model.";
  }

  // ── Execute each tool call against D1 ──────────────────────────────────
  // Append the assistant's tool_calls message
  messages.push({
    role: "assistant",
    content: "",
    tool_calls: pass1.tool_calls,
  });

  for (const call of pass1.tool_calls) {
    let args: Record<string, unknown> = {};
    try {
      args = JSON.parse(call.function.arguments);
    } catch {
      // malformed arguments — pass empty object, executor will handle
    }

    const result = await executeTool(db, call.function.name, args);

    messages.push({
      role: "tool",
      content: result,
      tool_call_id: call.id,
    });
  }

  // ── Pass 2: model synthesises a final answer with the tool data ────────
  const pass2 = (await ai.run(MODEL, {
    messages,
    tools,
    tool_choice: "none", // force text answer on second pass
  })) as { response?: string };

  return pass2.response ?? "No final response from model.";
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const { query } = (await request.json()) as { query?: string };
    if (!query?.trim()) {
      return Response.json({ error: "Missing 'query' field" }, { status: 400 });
    }

    try {
      const answer = await runAgentLoop(env.AI, env.DB, query);
      return Response.json({ answer });
    } catch (err) {
      return Response.json({ error: (err as Error).message }, { status: 500 });
    }
  },
};
```

---

## Anti-patterns

- **Injecting raw SQL into the prompt** — Exposes schema, enables prompt injection attacks, and produces ungrounded answers; define tools and let the model call them instead.
- **Skipping `tool_choice: "none"` on pass 2** — Without it the model may chain another tool call indefinitely; always force a text response on the final pass.
- **Parsing tool arguments without try/catch** — The model occasionally emits malformed JSON for arguments; always wrap `JSON.parse` and fall back gracefully.
- **No row limit on D1 queries** — An unbounded `listCampaigns` call can return thousands of rows, bloating the context window for pass 2; always apply `LIMIT`.

---

## Gotchas

- `tool_call_id` must round-trip exactly — the value from `pass1.tool_calls[n].id` must appear verbatim in the subsequent `tool` role message or the model will error.
- `@cf/meta/llama-3.3-70b-instruct-fp8-fast` may emit `tool_calls` with `arguments` as an already-stringified JSON string — always call `JSON.parse` even when it looks like an object.
- D1 prepared statements do not accept arrays as bind parameters; build dynamic `IN (?,?,?)` clauses with explicit bind slots.
- Workers AI enforces a combined input token limit; very large D1 result sets returned as tool messages can push pass 2 over the limit — truncate or paginate results before injecting them.

---

## Verification

```bash
# Seed D1 with test data
npx wrangler d1 execute ecommerce --local \
  --command "INSERT INTO orders VALUES ('ord-001','user@example.com','shipped',99.99,'2026-08-01')"

# Start dev server
npx wrangler dev --remote

# Ask about an order
curl -X POST http://localhost:8787 \
  -H 'Content-Type: application/json' \
  -d '{"query": "What is the status of order ord-001?"}'

# Ask about campaigns
curl -X POST http://localhost:8787 \
  -H 'Content-Type: application/json' \
  -d '{"query": "List all active email campaigns"}'
```

---

## Related

- `workers-ai-structured-output-json-schema.md`
- `workers-ai-embeddings-semantic-search-vectorize.md`

---

## Sources

- Cloudflare Workers AI tool calling docs — https://developers.cloudflare.com/workers-ai/function-calling/
- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
