# Long-Term AI Agent Memory Persistence with Durable Objects

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your AI agent forgets the conversation after every Worker request because Workers are stateless. You need per-session, multi-turn memory that survives cold starts, scales to thousands of concurrent users without a database, and compresses automatically when history grows too long.

## Context

Durable Objects (DOs) are single-threaded, location-aware stateful compute units with built-in persistent storage. A `MemoryDO` stores the conversation turns for one user session. Because each DO has its own isolated storage namespace keyed by `sessionId`, there is no cross-user data leakage. When history exceeds 40 turns the DO calls the LLM to produce a one-sentence-per-topic summary, replaces all but the last 10 turns with the summary, and continues — keeping the context window bounded.

Required bindings:
- `AI` — Workers AI
- `MEMORY_DO` — Durable Object namespace (`MemoryDO` class)

## Implementation

```typescript
// memory-do.ts  — the Durable Object
import { DurableObject } from 'cloudflare:workers';

type Turn = { role: 'user' | 'assistant' | 'system'; content: string; timestamp: number };
type Env = { AI: Ai };

const MAX_TURNS = 50;
const COMPRESS_AT = 40;
const KEEP_RECENT = 10;

export class MemoryDO extends DurableObject<Env> {
  private history: Turn[] = [];
  private loaded = false;

  // Load history from DO storage on first access (survives hibernation).
  private async ensureLoaded(): Promise<void> {
    if (this.loaded) return;
    const stored = await this.ctx.storage.get<Turn[]>('history');
    this.history = stored ?? [];
    this.loaded = true;
  }

  // RPC method: add a turn and persist.
  async addTurn(role: Turn['role'], content: string): Promise<void> {
    await this.ensureLoaded();
    this.history.push({ role, content, timestamp: Date.now() });

    // Compress when history is getting long.
    if (this.history.length >= COMPRESS_AT) {
      await this.compress();
    }

    // Hard cap: drop oldest turns beyond MAX_TURNS.
    if (this.history.length > MAX_TURNS) {
      this.history = this.history.slice(this.history.length - MAX_TURNS);
    }

    await this.ctx.storage.put('history', this.history);
  }

  // RPC method: return current history.
  async getHistory(): Promise<Turn[]> {
    await this.ensureLoaded();
    return this.history;
  }

  // RPC method: clear memory (e.g. explicit session reset).
  async clearHistory(): Promise<void> {
    this.history = [];
    this.loaded = true;
    await this.ctx.storage.delete('history');
  }

  // Summarise turns older than the most recent KEEP_RECENT.
  private async compress(): Promise<void> {
    const toSummarise = this.history.slice(0, this.history.length - KEEP_RECENT);
    const recent = this.history.slice(this.history.length - KEEP_RECENT);

    const contextText = toSummarise
      .map(t => `${t.role}: ${t.content}`)
      .join('\n');

    const result = await this.env.AI.run('@cf/meta/llama-3-8b-instruct', {
      messages: [
        {
          role: 'system',
          content:
            'Summarise the following conversation in bullet points. ' +
            'One bullet per distinct topic. Be concise.',
        },
        { role: 'user', content: contextText },
      ],
      max_tokens: 256,
    });

    const summary = (result as any).response as string;

    const summaryTurn: Turn = {
      role: 'system',
      content: `[Conversation summary up to this point]\n${summary}`,
      timestamp: Date.now(),
    };

    this.history = [summaryTurn, ...recent];
  }

  // Durable Object hibernation: the runtime calls fetch() on wake;
  // ensureLoaded() re-hydrates from storage transparently.
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const method = url.pathname.split('/').pop();

    if (request.method === 'POST' && method === 'addTurn') {
      const { role, content } = await request.json<{ role: Turn['role']; content: string }>();
      await this.addTurn(role, content);
      return new Response(JSON.stringify({ ok: true }), { headers: { 'Content-Type': 'application/json' } });
    }

    if (request.method === 'GET' && method === 'getHistory') {
      const history = await this.getHistory();
      return new Response(JSON.stringify(history), { headers: { 'Content-Type': 'application/json' } });
    }

    if (request.method === 'DELETE' && method === 'clearHistory') {
      await this.clearHistory();
      return new Response(JSON.stringify({ ok: true }), { headers: { 'Content-Type': 'application/json' } });
    }

    return new Response('Not found', { status: 404 });
  }
}
```

## Main Worker

```typescript
// worker.ts — entry-point that proxies memory calls to MemoryDO
type Env = { AI: Ai; MEMORY_DO: DurableObjectNamespace };

function getMemoryStub(env: Env, sessionId: string): DurableObjectStub {
  // One DO per sessionId — namespace isolation by design.
  const id = env.MEMORY_DO.idFromName(sessionId);
  return env.MEMORY_DO.get(id);
}

async function doFetch<T>(
  stub: DurableObjectStub,
  method: string,
  httpMethod: 'GET' | 'POST' | 'DELETE',
  body?: unknown,
): Promise<T> {
  const res = await stub.fetch(`http://do/${method}`, {
    method: httpMethod,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  return res.json<T>();
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const sessionId = url.searchParams.get('session') ?? 'default';
    const stub = getMemoryStub(env, sessionId);

    if (url.pathname === '/chat' && request.method === 'POST') {
      const { message } = await request.json<{ message: string }>();

      // Store user turn.
      await doFetch(stub, 'addTurn', 'POST', { role: 'user', content: message });

      // Retrieve full history for the LLM context.
      const history = await doFetch<{ role: string; content: string }[]>(
        stub, 'getHistory', 'GET',
      );

      // Call the LLM with accumulated history.
      const result = await env.AI.run('@cf/meta/llama-3-8b-instruct', {
        messages: history,
        max_tokens: 512,
      });
      const reply = (result as any).response as string;

      // Store assistant turn.
      await doFetch(stub, 'addTurn', 'POST', { role: 'assistant', content: reply });

      return new Response(JSON.stringify({ reply, turnCount: history.length + 1 }), {
        headers: { 'Content-Type': 'application/json' },
      });
    }

    if (url.pathname === '/history' && request.method === 'GET') {
      const history = await doFetch(stub, 'getHistory', 'GET');
      return new Response(JSON.stringify(history), {
        headers: { 'Content-Type': 'application/json' },
      });
    }

    if (url.pathname === '/reset' && request.method === 'DELETE') {
      await doFetch(stub, 'clearHistory', 'DELETE');
      return new Response(JSON.stringify({ ok: true }), {
        headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## wrangler.toml Configuration

```toml
[durable_objects]
bindings = [
  { name = "MEMORY_DO", class_name = "MemoryDO" }
]

[[migrations]]
tag = "v1"
new_classes = ["MemoryDO"]
```

## Anti-patterns

- **Storing history in KV** — KV is eventually consistent and has no locking; two concurrent requests for the same session will race and one will overwrite the other. DOs provide strong serialisation.
- **One DO for all sessions** — a single DO becomes a bottleneck and a cross-user data risk. Always key by `sessionId`.
- **Unbounded history** — LLMs have finite context windows; an ever-growing history will exceed the model's limit and cause errors. Compress proactively.
- **Awaiting the compression LLM call in the hot path** — if you call the LLM inside `addTurn` synchronously, every message that triggers compression will be slow. Consider scheduling compression via `ctx.storage.setAlarm`.

## Gotchas

- `DurableObject` hibernation (v2 DO runtime) means the in-memory `this.history` array is lost between requests. The `loaded` flag guards against a redundant storage read but must be reset to `false` after hibernation — the constructor re-initialises it to `false`, which is correct.
- `idFromName` is deterministic: the same `sessionId` string always maps to the same DO instance, across any Worker in the zone.
- DO storage `put` accepts any serialisable value; no JSON.stringify is needed.
- The `MemoryDO` class must be exported from the entry-point file (or re-exported) for wrangler to register the migration.

## Verification

```bash
# Start a conversation.
curl -X POST 'https://worker.example.com/chat?session=user-42' \
  -H 'Content-Type: application/json' \
  -d '{"message": "My name is Alice."}' | jq .reply

# Follow-up — agent should remember the name.
curl -X POST 'https://worker.example.com/chat?session=user-42' \
  -H 'Content-Type: application/json' \
  -d '{"message": "What is my name?"}' | jq .reply
# Expected: a response mentioning "Alice".

# Inspect stored history.
curl 'https://worker.example.com/history?session=user-42' | jq length
# Expected: 4 (2 user turns + 2 assistant turns).

# Reset session.
curl -X DELETE 'https://worker.example.com/reset?session=user-42'
```

## Related

- `rag-citation-grounding-vectorize-workers.md` — Vectorize for long-term knowledge retrieval alongside DO for short-term memory
- `llm-token-streaming-backpressure-workers.md` — streaming LLM responses from the same agent Worker
- `workers-ai-image-generation-r2-pipeline.md` — R2 + D1 persistence patterns

## Sources

- [Durable Objects — Overview](https://developers.cloudflare.com/durable-objects/)
- [Durable Objects — Storage API](https://developers.cloudflare.com/durable-objects/api/storage-api/)
- [Durable Objects — Hibernation](https://developers.cloudflare.com/durable-objects/reference/websockets/#websocket-hibernation)
- [Workers AI — LLaMA 3 8B Instruct](https://developers.cloudflare.com/workers-ai/models/llama-3-8b-instruct/)
