# AI Agent Tool-Call Retry with Idempotency via Durable Objects

- Date: 2026-08-22
- Author: example.com
- Status: production

## The Problem: Side-Effectful Tool Calls Cannot Be Naively Retried

LLM agents issue tool calls that interact with the outside world: sending emails,
charging payment cards, mutating database records, posting webhooks. When a Worker
crashes mid-flight — or the LLM decides to re-issue a tool call after a timeout —
naive retry logic executes the side effect twice. This is silent data corruption at
scale.

The standard fix — idempotency keys — is well-understood in REST APIs but awkward to
apply when the caller is an autonomous agent that does not know in advance which tools
it will invoke. Durable Objects solve this: they provide a single-threaded, persistent
execution context that can track exactly which tool calls are in-flight, which have
completed, and what their results were. At-most-once semantics become a first-class
property of the execution environment rather than a convention the agent must honour.

This pattern also enables resume-from-checkpoint: if the agent process is evicted, the
Durable Object persists the completed tool results and the agent can re-attach and
continue from the last known good state rather than re-running the entire trajectory.

## Context

- Runtime: Cloudflare Workers + Durable Objects
- Agent LLM: Workers AI or external LLM via AI Gateway
- Tool execution: any HTTP-callable side-effectful service
- Storage: Durable Object storage (tool call ledger), D1 (audit log)
- Language: TypeScript

## Idempotency Key Generation

Keys must be deterministic from the agent's perspective so the same logical tool call
always maps to the same key — even if the agent is resumed on a different Worker
instance. Hash the combination of session ID, tool name, and a content hash of the
arguments.

```ts
// src/idempotency.ts
export async function generateIdempotencyKey(
  sessionId: string,
  toolName: string,
  args: unknown
): Promise<string> {
  const payload = JSON.stringify({ sessionId, toolName, args });
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(payload)
  );
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
```

## Durable Object: Tool Call Ledger

The DO is the single source of truth for tool call state. It gates execution:
`pending` → `executing` → `completed` | `failed`. A call that arrives while a
matching key is already `executing` waits (or returns the cached result if complete).

```ts
// src/tool-ledger.ts
export interface ToolCallRecord {
  key: string;
  toolName: string;
  args: unknown;
  status: "pending" | "executing" | "completed" | "failed";
  result?: unknown;
  error?: string;
  startedAt: number;
  completedAt?: number;
  attemptCount: number;
}

export class ToolCallLedger implements DurableObject {
  private storage: DurableObjectStorage;

  constructor(state: DurableObjectState) {
    this.storage = state.storage;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const action = url.pathname.slice(1); // "acquire" | "complete" | "fail" | "get"
    const body = await request.json<{
      key: string;
      toolName?: string;
      args?: unknown;
      result?: unknown;
      error?: string;
    }>();

    switch (action) {
      case "acquire": {
        const existing = await this.storage.get<ToolCallRecord>(body.key);
        if (existing?.status === "completed") {
          // Cache hit — return stored result, skip execution
          return Response.json({ status: "cached", result: existing.result });
        }
        if (existing?.status === "executing") {
          // Another instance is running it — tell caller to wait
          return Response.json({ status: "in_progress" });
        }
        // Mark as executing — atomic within the DO
        const record: ToolCallRecord = {
          key: body.key,
          toolName: body.toolName!,
          args: body.args,
          status: "executing",
          startedAt: Date.now(),
          attemptCount: (existing?.attemptCount ?? 0) + 1,
        };
        await this.storage.put(body.key, record);
        return Response.json({ status: "acquired" });
      }

      case "complete": {
        const record = await this.storage.get<ToolCallRecord>(body.key);
        if (!record) return new Response("not found", { status: 404 });
        await this.storage.put(body.key, {
          ...record,
          status: "completed",
          result: body.result,
          completedAt: Date.now(),
        });
        return Response.json({ status: "ok" });
      }

      case "fail": {
        const record = await this.storage.get<ToolCallRecord>(body.key);
        if (!record) return new Response("not found", { status: 404 });
        await this.storage.put(body.key, {
          ...record,
          status: "failed",
          error: body.error,
          completedAt: Date.now(),
        });
        return Response.json({ status: "ok" });
      }

      case "get": {
        const record = await this.storage.get<ToolCallRecord>(body.key);
        return Response.json(record ?? null);
      }

      default:
        return new Response("unknown action", { status: 400 });
    }
  }
}
```

## Agent Tool Dispatcher with At-Most-Once Semantics

The dispatcher wraps every tool execution in the ledger acquire/complete/fail cycle.
It never executes a tool whose key is already `completed`; it re-raises the cached
result instead.

```ts
// src/agent-dispatcher.ts
import { generateIdempotencyKey } from "./idempotency";

export interface Env {
  TOOL_LEDGER: DurableObjectNamespace;
  AUDIT_DB: D1Database;
}

type ToolFn = (args: unknown) => Promise<unknown>;

async function ledgerCall(
  stub: DurableObjectStub,
  action: string,
  payload: object
): Promise<{ status: string; result?: unknown }> {
  const res = await stub.fetch(
    new Request(`https://do/${action}`, {
      method: "POST",
      body: JSON.stringify(payload),
      headers: { "Content-Type": "application/json" },
    })
  );
  return res.json();
}

export async function dispatchToolCall(
  sessionId: string,
  toolName: string,
  args: unknown,
  toolFn: ToolFn,
  env: Env
): Promise<unknown> {
  const key = await generateIdempotencyKey(sessionId, toolName, args);
  const id = env.TOOL_LEDGER.idFromName(sessionId);
  const stub = env.TOOL_LEDGER.get(id);

  // Acquire lock — handles cached, in_progress, and acquired states
  const acquire = await ledgerCall(stub, "acquire", { key, toolName, args });

  if (acquire.status === "cached") {
    console.log(`[${toolName}] cache hit, returning stored result`);
    return acquire.result;
  }

  if (acquire.status === "in_progress") {
    // Poll with backoff — another Worker is executing
    await new Promise((r) => setTimeout(r, 500));
    return dispatchToolCall(sessionId, toolName, args, toolFn, env);
  }

  // Execute the side-effectful tool exactly once
  try {
    const result = await toolFn(args);
    await ledgerCall(stub, "complete", { key, result });

    await env.AUDIT_DB.prepare(
      `INSERT INTO tool_audit (session_id, tool_name, idempotency_key, status, ts)
       VALUES (?, ?, ?, 'completed', unixepoch())`
    )
      .bind(sessionId, toolName, key)
      .run();

    return result;
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    await ledgerCall(stub, "fail", { key, error });
    throw err;
  }
}
```

## Resume-from-Checkpoint Pattern

When an agent session is re-attached after eviction, load all completed tool results
from the DO before issuing any new LLM calls. This lets the model re-construct its
tool call history without re-executing anything.

```ts
// src/agent-resume.ts
export async function loadCheckpoint(
  sessionId: string,
  toolKeys: string[],
  env: Env
): Promise<Map<string, unknown>> {
  const id = env.TOOL_LEDGER.idFromName(sessionId);
  const stub = env.TOOL_LEDGER.get(id);
  const results = new Map<string, unknown>();

  await Promise.all(
    toolKeys.map(async (key) => {
      const record = await ledgerCall(stub, "get", { key });
      if (record && (record as { status?: string }).status === "completed") {
        results.set(key, (record as { result?: unknown }).result);
      }
    })
  );

  return results;
}
```

## Anti-patterns

- Using the LLM's generated `tool_use_id` directly as the idempotency key — the model
  may generate different IDs on retry; always derive the key from stable inputs.
- Storing completed results in-memory on the Worker — eviction loses state; only the DO
  provides durability across Worker restarts.
- Treating `in_progress` as a terminal error — the correct response is to poll with
  backoff until the executing Worker completes or a watchdog timeout clears the lock.
- Setting DO names to random UUIDs per request — names must encode the session so
  all Workers handling the same session route to the same DO instance.

## Gotchas

- Durable Object `storage.put` is synchronous within the event loop but flushed
  asynchronously to disk; use `state.waitUntil` or `blockConcurrencyWhile` for
  transactions that must survive a crash between the put and the tool execution.
- The DO single-threaded model means `in_progress` polls will queue behind the
  executing fetch — this is the feature, not a bug.
- Idempotency keys based on args hashes are sensitive to argument serialisation order;
  always sort object keys before hashing.
- Watchdog TTL: set an alarm on the DO to auto-fail stuck `executing` records after
  a configurable timeout (e.g. 30 s) so a crashed Worker does not block the session.

## Verification

```ts
// test/idempotency.test.ts
import { generateIdempotencyKey } from "../src/idempotency";

const key1 = await generateIdempotencyKey("sess-1", "send_email", { to: "a@b.com" });
const key2 = await generateIdempotencyKey("sess-1", "send_email", { to: "a@b.com" });
const key3 = await generateIdempotencyKey("sess-1", "send_email", { to: "x@y.com" });

console.assert(key1 === key2, "same args must produce same key");
console.assert(key1 !== key3, "different args must produce different key");
console.log("idempotency key test passed");
```

## Related

- [Agent Tool Design](agent-tool-design.md)
- [Agent Error Recovery](../agents/AGENT_ERROR_RECOVERY.md)
- [Agent Memory Long-Term](../agents/LONG_TERM_MEMORY.md)
- [Agent Observability Tracing](agent-observability-tracing.md)
- [Agent Multi-Agent Orchestration](agent-multi-agent-orchestration.md)

## Sources

- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/durable-objects/api/alarms/
- https://www.anthropic.com/research/building-effective-agents
- https://developers.cloudflare.com/queues/
- https://stripe.com/docs/api/idempotent_requests
