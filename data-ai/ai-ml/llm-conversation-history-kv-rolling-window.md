# LLM Conversation History KV Rolling Window

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your chatbot Worker needs to maintain multi-turn conversation context across HTTP
requests, but Workers are stateless. You need each user's message history to be
available on the next request, survive Worker restarts, and never exceed the model's
context window. You want the simplest possible solution without running a separate
database.

## Context

Cloudflare KV is eventually consistent, globally replicated, and ideal for
read-heavy session data. A rolling window strategy keeps only the N most recent
messages in KV, evicting the oldest automatically. Paired with a token-counting
heuristic, you can cap the window by tokens rather than message count, which is
more accurate for models with strict context limits.

KV TTL (time-to-live) handles session expiry automatically, removing the need for
a separate cleanup job.

---

## 1. Data Shape and KV Key Convention

```typescript
// src/conversation.ts
export interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

export interface ConversationState {
  messages: Message[];
  updatedAt: number; // Unix ms
}

function kvKey(sessionId: string): string {
  return `conv:${sessionId}`;
}
```

Keep the key namespaced (`conv:`) so the KV namespace can be shared with other
session data without collisions.

---

## 2. Loading History from KV

```typescript
// src/conversation.ts (continued)
const SESSION_TTL_SECONDS = 60 * 60 * 2; // 2 hours

export async function loadHistory(
  kv: KVNamespace,
  sessionId: string
): Promise<Message[]> {
  const raw = await kv.get(kvKey(sessionId), 'text');
  if (!raw) return [];

  try {
    const state: ConversationState = JSON.parse(raw);
    return state.messages;
  } catch {
    // Corrupted value — start fresh
    return [];
  }
}
```

---

## 3. Saving History with Rolling Eviction

```typescript
// src/conversation.ts (continued)

// Approximate token count: 1 token ≈ 4 characters (English)
function estimateTokens(messages: Message[]): number {
  return messages.reduce(
    (sum, m) => sum + Math.ceil(m.content.length / 4),
    0
  );
}

const MAX_TOKENS = 3_000; // leave headroom for system prompt + completion
const MAX_MESSAGES = 40;  // hard cap regardless of token count

export async function saveHistory(
  kv: KVNamespace,
  sessionId: string,
  messages: Message[]
): Promise<void> {
  // Roll by message count first
  let trimmed = messages.slice(-MAX_MESSAGES);

  // Then roll by estimated token budget
  while (trimmed.length > 2 && estimateTokens(trimmed) > MAX_TOKENS) {
    // Remove the oldest non-system message
    const firstNonSystem = trimmed.findIndex((m) => m.role !== 'system');
    if (firstNonSystem === -1) break;
    trimmed = [
      ...trimmed.slice(0, firstNonSystem),
      ...trimmed.slice(firstNonSystem + 1),
    ];
  }

  const state: ConversationState = {
    messages: trimmed,
    updatedAt: Date.now(),
  };

  await kv.put(kvKey(sessionId), JSON.stringify(state), {
    expirationTtl: SESSION_TTL_SECONDS,
  });
}
```

Eviction removes the oldest **non-system** message first, preserving any static
system prompt that was prepended to the history.

---

## 4. Worker Request Handler

```typescript
// src/index.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { sessionId, userMessage } = await req.json<{
      sessionId: string;
      userMessage: string;
    }>();

    if (!sessionId || !userMessage) {
      return new Response('Missing sessionId or userMessage', { status: 400 });
    }

    // 1. Load existing history
    const history = await loadHistory(env.CONVERSATION_KV, sessionId);

    // 2. Append the new user turn
    history.push({ role: 'user', content: userMessage });

    // 3. Call the LLM with full history as context
    const response = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
      messages: history,
      max_tokens: 512,
    });

    const assistantMessage = response.response ?? '';

    // 4. Append assistant reply and persist
    history.push({ role: 'assistant', content: assistantMessage });
    await saveHistory(env.CONVERSATION_KV, sessionId, history);

    return Response.json({ reply: assistantMessage });
  },
};
```

---

## 5. Session ID Generation and Security

```typescript
// src/session.ts
import { createHmac } from 'node:crypto'; // available in Workers runtime

export function generateSessionId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

// Validate a session ID belongs to a user (if you sign them)
export function signSessionId(sessionId: string, secret: string): string {
  const hmac = createHmac('sha256', secret);
  hmac.update(sessionId);
  return `${sessionId}.${hmac.digest('hex').slice(0, 16)}`;
}

export function validateSignedSessionId(
  signed: string,
  secret: string
): string | null {
  const [id, sig] = signed.split('.');
  if (!id || !sig) return null;
  const expected = signSessionId(id, secret).split('.')[1];
  return expected === sig ? id : null;
}
```

Sign session IDs so clients cannot probe arbitrary sessions by guessing IDs.

---

## 6. wrangler.toml Binding

```toml
# wrangler.toml
[[kv_namespaces]]
binding = "CONVERSATION_KV"
id = "your-kv-namespace-id"
```

```typescript
// src/env.d.ts
interface Env {
  CONVERSATION_KV: KVNamespace;
  AI: Ai;
  SESSION_SECRET: string; // set as a secret via: wrangler secret put SESSION_SECRET
}
```

---

## Anti-patterns

- **Storing unbounded history** — KV values are limited to 25 MB, but even well below
  that limit, sending 10 000-message history to the model wastes tokens and money.
- **Using `sessionId` directly from a client-controlled cookie without validation** —
  any user can read any session by guessing IDs if they are sequential or short.
- **Writing history on every intermediate streaming chunk** — only write to KV after
  the complete assistant response is received, not on each streamed token.
- **Keeping system prompts inside the rolling history** — a system prompt should be
  prepended fresh on each request from a separate config store, not stored in KV
  alongside user messages where it can be evicted by rolling logic.
- **Relying on KV strong consistency for deduplication** — KV is eventually consistent;
  two rapid concurrent requests for the same session can produce a history race. Use
  Durable Objects if strict ordering matters.

---

## Gotchas

- KV `expirationTtl` resets on every write, so an active session that is written every
  few seconds will never expire — the TTL is relative to the most recent write, not
  to session creation.
- KV `put` is fire-and-forget in the sense that it returns before the value is
  globally replicated. Reads in other regions may briefly see stale data.
- `getRandomValues` is available globally in the Workers runtime; `crypto.subtle` is
  also available. The `node:crypto` `createHmac` requires the `nodejs_compat`
  compatibility flag in `wrangler.toml`.
- KV writes are billed per-operation regardless of value size. Saving history on
  every turn at high QPS can add up; consider writing only when the history actually
  changed (i.e., skip writes for read-only health checks).

---

## Verification

```typescript
// Integration test
async function testRollingEviction(kv: KVNamespace) {
  const sessionId = 'test-session-001';

  // Fill history beyond MAX_MESSAGES
  const messages: Message[] = Array.from({ length: 50 }, (_, i) => ({
    role: (i % 2 === 0 ? 'user' : 'assistant') as Message['role'],
    content: `Message number ${i}`,
  }));

  await saveHistory(kv, sessionId, messages);
  const loaded = await loadHistory(kv, sessionId);

  console.assert(loaded.length <= 40, `Expected ≤40 messages, got ${loaded.length}`);
  console.assert(
    loaded[loaded.length - 1].content === 'Message number 49',
    'Most recent message must be preserved'
  );
}
```

---

## Related

- `agent-memory-short-term.md`
- `llm-context-window-cloudflare-workers.md`
- `llm-context-window-management.md`
- `workers-ai-durable-objects-stateful-sessions.md`

---

## Sources

- Cloudflare KV docs: https://developers.cloudflare.com/kv/
- Cloudflare Workers AI — supported models: https://developers.cloudflare.com/workers-ai/models/
- KV limits (25 MB value, TTL): https://developers.cloudflare.com/kv/platform/limits/
