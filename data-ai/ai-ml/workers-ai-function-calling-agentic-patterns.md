# Workers AI Function Calling — Agentic Tool-Use Patterns
- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You want to build an agentic workflow inside a Cloudflare Worker where an LLM can
decide, at runtime, to call one of several tools (database lookup, external API,
vector search, computation) and loop until it has enough information to produce a
final answer — without a separate backend server.

## Context

Cloudflare Workers AI exposes function-calling / tool-use through the standard
`tools` parameter on compatible models (`@cf/meta/llama-3.1-8b-instruct`,
`@cf/mistral/mistral-7b-instruct-v0.2`, etc.). The binding is synchronous per
turn, so you orchestrate the agent loop yourself in Worker code. Each turn costs
one AI Gateway request; D1 or KV can checkpoint state so the loop can survive
the 30 s CPU wall-clock limit by re-entering across requests.

Key constraints for the pattern:
- Workers AI `run()` is async and accepts the full `tools` array on each call.
- Tool results are injected back as `role: "tool"` messages.
- The loop must detect a final `stop_reason: "end_turn"` (no tool calls) or a
  configured maximum-turns guard to prevent runaway billing.
- Mobile callers need compact tool output — strip verbose fields before appending
  to context; target < 4 KB per tool result to keep total context small.

---

## Section 1 — Binding and Model Configuration

```toml
# wrangler.toml
[ai]
binding = "AI"

[[d1_databases]]
binding    = "DB"
database_name = "agent_checkpoints"
database_id   = "xxxx-yyyy-zzzz"
```

```typescript
// src/index.ts
export interface Env {
  AI: Ai;
  DB: D1Database;
}
```

Define tools once as a typed constant — this gets serialised on every turn, so
keep descriptions concise (< 120 chars each).

```typescript
const TOOLS: AiTextGenerationToolInput[] = [
  {
    name: "search_products",
    description: "Full-text search across the product catalogue. Returns up to 5 matches.",
    parameters: {
      type: "object",
      properties: {
        query:    { type: "string", description: "Search phrase" },
        max_price: { type: "number", description: "Optional upper price limit in USD" },
      },
      required: ["query"],
    },
  },
  {
    name: "get_order_status",
    description: "Fetch order details by order ID.",
    parameters: {
      type: "object",
      properties: {
        order_id: { type: "string" },
      },
      required: ["order_id"],
    },
  },
  {
    name: "calculate_shipping",
    description: "Estimate shipping cost given product weight (kg) and destination country.",
    parameters: {
      type: "object",
      properties: {
        weight_kg:   { type: "number" },
        destination: { type: "string", description: "ISO 3166-1 alpha-2 country code" },
      },
      required: ["weight_kg", "destination"],
    },
  },
];
```

---

## Section 2 — The Agent Loop

The loop runs inside a single Worker request. If the conversation is long-lived
(chat UI with multiple user turns) each HTTP request reconstructs the message
history from D1 rather than keeping it in memory.

```typescript
const MAX_TURNS = 6; // guard against infinite tool loops

async function runAgent(
  env: Env,
  userMessage: string,
  sessionId: string,
  isMobile: boolean,
): Promise<string> {
  // 1. Load or initialise message history
  const messages: RoleScopedChatInput[] = await loadHistory(env.DB, sessionId);

  messages.push({ role: "user", content: userMessage });

  let turn = 0;

  while (turn < MAX_TURNS) {
    turn++;

    const response = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
      messages,
      tools: TOOLS,
      // Keep max_tokens tight for tool calls; the final answer can be longer
      max_tokens: turn < MAX_TURNS ? 512 : 1024,
      stream: false,
    });

    const choice = (response as AiTextGenerationOutput).response ?? "";
    const toolCalls = (response as any).tool_calls as ToolCall[] | undefined;

    // 2a. No tool calls → final answer
    if (!toolCalls || toolCalls.length === 0) {
      const finalAnswer = isMobile ? summariseForMobile(choice) : choice;
      messages.push({ role: "assistant", content: finalAnswer });
      await saveHistory(env.DB, sessionId, messages);
      return finalAnswer;
    }

    // 2b. Execute each tool call and collect results
    messages.push({ role: "assistant", content: choice, tool_calls: toolCalls });

    for (const call of toolCalls) {
      const result = await dispatchTool(env, call, isMobile);
      messages.push({
        role: "tool",
        tool_call_id: call.id,
        content: JSON.stringify(result),
      });
    }
  }

  // Exceeded max turns — return a graceful fallback
  await saveHistory(env.DB, sessionId, messages);
  return "I wasn't able to complete your request within the allowed steps. Please rephrase or narrow your question.";
}
```

---

## Section 3 — Tool Dispatch and Mobile Compaction

```typescript
interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

async function dispatchTool(
  env: Env,
  call: ToolCall,
  isMobile: boolean,
): Promise<unknown> {
  switch (call.name) {
    case "search_products":
      return searchProducts(env, call.arguments as any, isMobile);
    case "get_order_status":
      return getOrderStatus(env, call.arguments as any, isMobile);
    case "calculate_shipping":
      return calculateShipping(call.arguments as any);
    default:
      return { error: `Unknown tool: ${call.name}` };
  }
}

async function searchProducts(
  env: Env,
  args: { query: string; max_price?: number },
  isMobile: boolean,
) {
  const rows = await env.DB.prepare(
    `SELECT id, name, price_usd, description
       FROM products
      WHERE name LIKE ?1
        AND (?2 IS NULL OR price_usd <= ?2)
      LIMIT 5`,
  )
    .bind(`%${args.query}%`, args.max_price ?? null)
    .all();

  if (isMobile) {
    // Strip description to keep context window lean on mobile
    return rows.results.map((r: any) => ({ id: r.id, name: r.name, price: r.price_usd }));
  }
  return rows.results;
}

async function getOrderStatus(
  env: Env,
  args: { order_id: string },
  isMobile: boolean,
) {
  const row = await env.DB.prepare(
    `SELECT id, status, shipped_at, tracking_url FROM orders WHERE id = ?1`,
  )
    .bind(args.order_id)
    .first();

  if (!row) return { error: "Order not found" };

  // On mobile, omit tracking URL (long string wastes tokens)
  if (isMobile) {
    return { id: row.id, status: row.status, shipped_at: row.shipped_at };
  }
  return row;
}

function calculateShipping(args: { weight_kg: number; destination: string }) {
  // Simple heuristic — replace with a real rates table
  const base = args.destination === "US" ? 5 : 15;
  const cost = base + args.weight_kg * 2;
  return { estimated_usd: cost.toFixed(2), currency: "USD" };
}

function summariseForMobile(text: string): string {
  // Truncate to ~300 words on mobile to reduce render time
  const words = text.split(/\s+/);
  if (words.length <= 300) return text;
  return words.slice(0, 300).join(" ") + "…";
}
```

---

## Section 4 — Conversation Persistence with D1

```typescript
async function loadHistory(db: D1Database, sessionId: string): Promise<RoleScopedChatInput[]> {
  const row = await db
    .prepare("SELECT messages FROM agent_sessions WHERE id = ?1")
    .bind(sessionId)
    .first<{ messages: string }>();

  if (!row) return [{ role: "system", content: "You are a helpful shopping assistant." }];
  return JSON.parse(row.messages);
}

async function saveHistory(
  db: D1Database,
  sessionId: string,
  messages: RoleScopedChatInput[],
): Promise<void> {
  // Keep only the last 20 messages to bound context size
  const trimmed = messages.slice(-20);
  await db
    .prepare(
      `INSERT INTO agent_sessions (id, messages, updated_at)
       VALUES (?1, ?2, datetime('now'))
       ON CONFLICT (id) DO UPDATE SET messages = excluded.messages, updated_at = excluded.updated_at`,
    )
    .bind(sessionId, JSON.stringify(trimmed))
    .run();
}
```

D1 schema:

```sql
CREATE TABLE IF NOT EXISTS agent_sessions (
  id         TEXT PRIMARY KEY,
  messages   TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

---

## Anti-patterns

- **Unbounded loops** — omitting a max-turns guard lets a confused model call tools
  indefinitely, burning AI Gateway quota and hitting the 30 s CPU limit.
- **Full DB rows as tool results** — injecting wide result sets (10+ columns, 20+ rows)
  bloats the context window fast; always select only the columns the LLM needs.
- **Reconstructing tools inside the loop** — re-allocating the `TOOLS` array on every
  iteration is wasteful; define it at module scope.
- **Ignoring mobile context size** — a mobile client with a slow connection suffers if
  the final response is 3 000 tokens; apply `summariseForMobile` before returning.
- **Storing raw tool_calls in D1 without normalisation** — the `tool_calls` field
  format is model-specific; if you switch models mid-session the stored history may
  not deserialise correctly. Version your stored schema.

---

## Gotchas

- Workers AI `run()` returns `tool_calls` only when the model decides to call a tool.
  Some model versions return an empty array instead of omitting the field — check
  both `!toolCalls` and `toolCalls.length === 0`.
- The `tool_call_id` on the `"tool"` message must match the `id` in `tool_calls`
  exactly; a mismatch causes the model to hallucinate tool results.
- Llama 3.1 8B occasionally emits tool call JSON inside the `response` text field
  as a fallback when it cannot format the structured output. Add a regex guard to
  detect and parse this.
- AI Gateway logs each `run()` call as a separate request; set a spend alert at
  the Gateway project level so an agent loop gone wrong does not drain your budget.
- D1 `prepare().bind()` with `null` does not reliably map to SQL `NULL` in all
  runtimes — use `IS NULL OR price_usd <= ?2` rather than just `price_usd <= ?2`.

---

## Verification

```typescript
// Unit test — stub env.AI.run to return canned tool_calls then a final answer
import { expect, test, vi } from "vitest";

test("agent resolves in two turns", async () => {
  const mockAI = {
    run: vi.fn()
      .mockResolvedValueOnce({
        response: "",
        tool_calls: [{ id: "c1", name: "search_products", arguments: { query: "headphones" } }],
      })
      .mockResolvedValueOnce({ response: "I found 3 headphone options.", tool_calls: [] }),
  };
  const mockDB = {
    prepare: () => ({ bind: () => ({ first: async () => null, run: async () => {} }) }),
  };

  const answer = await runAgent(
    { AI: mockAI, DB: mockDB } as any,
    "Show me headphones",
    "test-session",
    false,
  );

  expect(mockAI.run).toHaveBeenCalledTimes(2);
  expect(answer).toContain("headphone");
});
```

---

## Related

- `llm-function-calling-tool-use-patterns.md` — provider-agnostic tool-use patterns
- `agent-planning-react.md` — ReAct reasoning loop design
- `ai-gateway-rate-limiting.md` — per-project spend guards
- `agent-memory-short-term.md` — in-request context management
- `agent-error-recovery.md` — handling tool failures gracefully

---

## Sources

- Cloudflare Workers AI tool use documentation: https://developers.cloudflare.com/workers-ai/function-calling/
- Llama 3.1 function calling guide: https://llama.meta.com/docs/model-cards-and-prompt-formats/llama3_1/
- D1 query binding docs: https://developers.cloudflare.com/d1/worker-api/d1-database/
