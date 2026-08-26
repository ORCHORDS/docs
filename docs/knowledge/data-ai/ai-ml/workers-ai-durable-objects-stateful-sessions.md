# Workers AI Stateful Sessions with Durable Objects

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Every Workers AI inference call is stateless: the platform has no built-in memory of
prior turns. Building a multi-turn chat application means you must re-send the full
conversation history on every request. Without server-side session storage you either
bloat request payloads (pushing against context-window limits) or lose history when the
client refreshes. You need per-user conversation state that survives Worker restarts,
stays consistent across concurrent requests from the same user, and scales without a
separate database.

## Context

Durable Objects (DOs) give Workers a single-threaded, co-located storage primitive with
strong consistency guarantees. A `DurableObjectStub` is addressed by an ID derived from
a logical key (e.g., `userId`), so every request from the same user always routes to
the same DO instance in the same Cloudflare data-centre that owns that ID.

Combining DOs with Workers AI gives you:
- Persistent conversation history stored inside the DO's `storage` API.
- At-most-one concurrent AI call per session, avoiding race conditions from rapid
  multi-tab clicks.
- Context-window budget enforcement before each call.
- Optional summarisation of old turns to keep history within token limits.

Pricing note: DO storage is billed per GB-month; typical chat session objects are
small (≪ 1 KB per turn).

## Durable Object: Session Store

```typescript
// src/chat-session.ts
import type { DurableObjectState, Env } from "./types";

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

const SYSTEM_PROMPT: ChatMessage = {
  role: "system",
  content: "You are a concise, helpful assistant.",
};

const MAX_HISTORY_TOKENS = 3000;   // conservative budget
const APPROX_CHARS_PER_TOKEN = 4;

export class ChatSession {
  private state: DurableObjectState;
  private env: Env;
  private history: ChatMessage[] = [];
  private loaded = false;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  /** Lazily load history from DO storage on first access. */
  private async ensureLoaded(): Promise<void> {
    if (this.loaded) return;
    const stored = await this.state.storage.get<ChatMessage[]>("history");
    this.history = stored ?? [];
    this.loaded = true;
  }

  /** Trim history so total character count stays under budget. */
  private trimHistory(): void {
    const budget = MAX_HISTORY_TOKENS * APPROX_CHARS_PER_TOKEN;
    let total = this.history.reduce((sum, m) => sum + m.content.length, 0);
    while (total > budget && this.history.length > 0) {
      const removed = this.history.shift()!;
      total -= removed.content.length;
    }
  }

  async fetch(request: Request): Promise<Response> {
    const path = new URL(request.url).pathname;

    if (path === "/chat" && request.method === "POST") {
      return this.handleChat(request);
    }
    if (path === "/history" && request.method === "GET") {
      return this.handleHistory();
    }
    if (path === "/reset" && request.method === "DELETE") {
      return this.handleReset();
    }
    return new Response("Not found", { status: 404 });
  }

  private async handleChat(request: Request): Promise<Response> {
    const { message } = (await request.json()) as { message: string };
    if (!message?.trim()) {
      return new Response("message is required", { status: 400 });
    }

    await this.ensureLoaded();

    this.history.push({ role: "user", content: message });
    this.trimHistory();

    const messages: ChatMessage[] = [SYSTEM_PROMPT, ...this.history];

    const result = await this.env.AI.run(
      "@cf/meta/llama-3.1-8b-instruct",
      { messages, max_tokens: 512, temperature: 0.7 },
    );

    const assistantText =
      typeof result === "object" && "response" in result
        ? (result as { response: string }).response
        : "";

    this.history.push({ role: "assistant", content: assistantText });

    // Persist updated history
    await this.state.storage.put("history", this.history);

    return Response.json({ response: assistantText, turns: this.history.length });
  }

  private async handleHistory(): Promise<Response> {
    await this.ensureLoaded();
    return Response.json({ history: this.history });
  }

  private async handleReset(): Promise<Response> {
    this.history = [];
    this.loaded = true;
    await this.state.storage.delete("history");
    return new Response("Session cleared", { status: 200 });
  }
}
```

## Worker Entry Point: Routing to the Right Session

```typescript
// src/index.ts
import { ChatSession } from "./chat-session";

export { ChatSession };

export interface Env {
  AI: Ai;
  CHAT_SESSION: DurableObjectNamespace;
}

/**
 * Derive a deterministic session ID from the request.
 * In production: extract from a verified JWT or session cookie.
 */
function getSessionId(request: Request, env: Env): DurableObjectId {
  const sessionToken = request.headers.get("X-Session-Token") ?? "anonymous";
  // idFromName() guarantees the same ID for the same string, globally
  return env.CHAT_SESSION.idFromName(sessionToken);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const id = getSessionId(request, env);
    const stub = env.CHAT_SESSION.get(id);

    // Forward the request to the DO, preserving path + body
    const doUrl = new URL(request.url);
    doUrl.hostname = "do-internal";  // hostname ignored internally

    return stub.fetch(
      new Request(doUrl.toString(), {
        method: request.method,
        headers: request.headers,
        body: request.body,
      }),
    );
  },
};
```

```jsonc
// wrangler.jsonc
{
  "name": "stateful-chat",
  "compatibility_date": "2025-09-01",
  "ai": { "binding": "AI" },
  "durable_objects": {
    "bindings": [
      { "name": "CHAT_SESSION", "class_name": "ChatSession" }
    ]
  },
  "migrations": [
    { "tag": "v1", "new_classes": ["ChatSession"] }
  ]
}
```

## Context-Window Summarisation

When history grows large, summarise old turns instead of discarding them:

```typescript
// src/summariser.ts
import type { Env } from "./types";
import type { ChatMessage } from "./chat-session";

export async function summariseOldTurns(
  turns: ChatMessage[],
  env: Env,
): Promise<ChatMessage> {
  const text = turns
    .map((m) => `${m.role.toUpperCase()}: ${m.content}`)
    .join("\n");

  const result = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [
      {
        role: "system",
        content: "Summarise the following conversation in ≤80 words, preserving key facts.",
      },
      { role: "user", content: text },
    ],
    max_tokens: 200,
    temperature: 0.2,
  });

  const summary =
    typeof result === "object" && "response" in result
      ? (result as { response: string }).response
      : "(summary unavailable)";

  return { role: "assistant", content: `[Previous context summary]: ${summary}` };
}
```

Integrate in `ChatSession.trimHistory()`: when the character budget is exceeded, pass
the oldest 50 % of turns to `summariseOldTurns`, replace them with the summary
message, then continue.

## Concurrent-Request Safety

The DO's single-threaded model serialises requests automatically. However, rapid
double-submissions (e.g., a user clicking "Send" twice) can queue two AI calls and
produce duplicate replies. Guard with an in-memory lock:

```typescript
// Inside ChatSession class
private inferring = false;

private async handleChat(request: Request): Promise<Response> {
  if (this.inferring) {
    return new Response(
      JSON.stringify({ error: "A response is already being generated." }),
      { status: 429, headers: { "Content-Type": "application/json" } },
    );
  }
  this.inferring = true;
  try {
    // ... AI call as before ...
  } finally {
    this.inferring = false;
  }
}
```

## Anti-patterns

- **Using `idFromRandom()` for session IDs**: generates a new DO on every request;
  history is lost immediately. Always use `idFromName(stableKey)`.
- **Storing full history in the Worker's in-memory KV or Cache API**: Cache API has
  no consistency guarantees and can be evicted; in-memory state is lost on Worker
  restart. Use DO `storage`.
- **Sending history to the client and echoing it back**: leaks conversation data to
  the network, inflates payloads, and allows client tampering. Keep history server-side.
- **Not trimming history before calling AI**: sending 200 turns exceeds context windows
  and causes `400 context_length_exceeded` errors.
- **Skipping the migration tag**: omitting `migrations` in `wrangler.jsonc` causes
  deployment to fail when you first add the DO class.

## Gotchas

- **DO location pinning**: the DO is created in the Cloudflare region closest to the
  first request from that `idFromName()` key. Subsequent requests from geographically
  distant users route to that region, adding latency. Use `locationHint` in
  `env.CHAT_SESSION.get(id, { locationHint: "enam" })` for region hints if users are
  known to be in one geography.
- **DO hibernation**: idle DOs are evicted from memory after ~10 s of inactivity;
  in-memory fields (`this.history`, `this.loaded`) are lost. Always re-read from
  `storage` on eviction (the `ensureLoaded()` pattern handles this).
- **Storage is transactional but not streamed**: `storage.put()` is durable only after
  the `await` resolves. If the Worker crashes between the AI call and `storage.put()`,
  the assistant turn is lost. Consider optimistic writes or idempotency keys.
- **`state.storage.list()` returns all keys**: for debugging only—avoid in hot paths.

## Verification

```bash
# Start a new session
SESSION="user-test-001"
curl -s -X POST https://stateful-chat.example.workers.dev/chat \
  -H "X-Session-Token: $SESSION" \
  -H "Content-Type: application/json" \
  -d '{"message":"My name is Alice."}' | jq .

# Continue the session — DO remembers Alice
curl -s -X POST https://stateful-chat.example.workers.dev/chat \
  -H "X-Session-Token: $SESSION" \
  -H "Content-Type: application/json" \
  -d '{"message":"What is my name?"}' | jq .response

# Inspect stored history
curl -s https://stateful-chat.example.workers.dev/history \
  -H "X-Session-Token: $SESSION" | jq .history | wc -l

# Reset session
curl -s -X DELETE https://stateful-chat.example.workers.dev/reset \
  -H "X-Session-Token: $SESSION"
```

## Related

- `llm-context-window-cloudflare-workers.md`
- `llm-context-window-management.md`
- `agent-memory-short-term.md`
- `agent-memory-long-term.md`
- `workers-ai-function-calling-agentic-patterns.md`
- `llm-async-patterns.md`

## Sources

- Cloudflare Durable Objects docs: https://developers.cloudflare.com/durable-objects/
- DO storage API: https://developers.cloudflare.com/durable-objects/api/storage-api/
- Workers AI binding reference: https://developers.cloudflare.com/workers-ai/configuration/bindings/
- Context window limits by model: https://developers.cloudflare.com/workers-ai/models/
