# LLM Conversation Summarization with KV Context Compression

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A long-running chat session accumulates hundreds of turns, pushing the context window to its limit and inflating inference costs. A rolling-window drop discards older turns entirely and breaks conversational continuity. You need to periodically summarize older turns into a compact "memory block" stored in KV, so the model receives the summary plus recent turns instead of the full raw history.

## Context

Workers AI and AI Gateway both accept a `messages` array. When that array grows beyond a configurable token threshold, a summarization pass runs: the oldest N turns are removed from the live array, compressed into a single assistant-authored summary, stored in KV, and prepended to the next request as a system-level memory. Recent turns (last K) are always kept verbatim for coherence.

---

## Conversation Store in KV

```typescript
// conversation-store.ts
export interface Turn {
  role: "user" | "assistant" | "system";
  content: string;
  ts: number;
}

export interface ConversationState {
  sessionId: string;
  summary: string | null;       // compressed memory of older turns
  recentTurns: Turn[];          // verbatim recent turns
  totalTurns: number;
  lastUpdated: number;
}

const RECENT_TURNS_KEEP = 10;   // always keep last N turns verbatim
const SUMMARIZE_THRESHOLD = 20; // summarize when total turns exceed this
const KV_TTL = 86_400 * 7;     // 7-day session expiry

export async function loadConversation(
  kv: KVNamespace,
  sessionId: string
): Promise<ConversationState> {
  const stored = await kv.get<ConversationState>(`conv:${sessionId}`, "json");
  return stored ?? {
    sessionId,
    summary: null,
    recentTurns: [],
    totalTurns: 0,
    lastUpdated: Date.now()
  };
}

export async function saveConversation(
  kv: KVNamespace,
  state: ConversationState
): Promise<void> {
  await kv.put(`conv:${state.sessionId}`, JSON.stringify({
    ...state,
    lastUpdated: Date.now()
  }), { expirationTtl: KV_TTL });
}
```

---

## Token Estimation

Lightweight approximation to avoid a full tokenizer call on every turn.

```typescript
// token-estimator.ts
export function estimateTokens(messages: { content: string }[]): number {
  // ~4 chars per token, 4-token overhead per message
  return messages.reduce((sum, m) => sum + Math.ceil(m.content.length / 4) + 4, 0);
}

export function needsSummarization(state: ConversationState): boolean {
  return state.totalTurns >= SUMMARIZE_THRESHOLD &&
    state.recentTurns.length > RECENT_TURNS_KEEP;
}
```

---

## Summarization Pass

```typescript
// summarizer.ts
const SUMMARIZE_SYSTEM = `You are a conversation memory manager.
Summarize the provided conversation turns into a concise, factual memory block (max 200 words).
Preserve: key facts, decisions, user preferences, named entities, open questions.
Omit: pleasantries, filler, repeated information.
Write in third-person neutral: "The user asked about X. The assistant explained Y."`;

export async function summarizeTurns(
  ai: Ai,
  turnsToSummarize: Turn[],
  existingSummary: string | null
): Promise<string> {
  const history = turnsToSummarize
    .map(t => `${t.role.toUpperCase()}: ${t.content}`)
    .join("\n");

  const context = existingSummary
    ? `Previous summary:\n${existingSummary}\n\nNew turns to incorporate:\n${history}`
    : history;

  const result = await ai.run("@cf/mistral/mistral-7b-instruct-v0.1", {
    messages: [
      { role: "system", content: SUMMARIZE_SYSTEM },
      { role: "user", content: context }
    ],
    max_tokens: 300,
    temperature: 0.2
  }) as { response: string };

  return result.response.trim();
}
```

---

## Context Assembly for LLM Request

```typescript
// context-builder.ts
export function buildMessages(
  state: ConversationState,
  systemPrompt: string,
  newUserMessage: string
): { role: string; content: string }[] {
  const messages: { role: string; content: string }[] = [];

  // 1. Base system prompt
  messages.push({ role: "system", content: systemPrompt });

  // 2. Compressed memory block (if any)
  if (state.summary) {
    messages.push({
      role: "system",
      content: `[Conversation Memory — earlier context]\n${state.summary}`
    });
  }

  // 3. Verbatim recent turns
  for (const turn of state.recentTurns) {
    messages.push({ role: turn.role, content: turn.content });
  }

  // 4. New user message
  messages.push({ role: "user", content: newUserMessage });

  return messages;
}
```

---

## Worker Chat Handler

```typescript
// worker.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { sessionId, message, systemPrompt = "You are a helpful assistant." } =
      await req.json<{ sessionId: string; message: string; systemPrompt?: string }>();

    if (!sessionId || !message) {
      return Response.json({ error: "sessionId and message required" }, { status: 400 });
    }

    // Load conversation state
    let state = await loadConversation(env.KV, sessionId);

    // Summarize if threshold reached
    if (needsSummarization(state)) {
      const turnsToCompress = state.recentTurns.slice(0, state.recentTurns.length - RECENT_TURNS_KEEP);
      const newSummary = await summarizeTurns(env.AI, turnsToCompress, state.summary);
      state = {
        ...state,
        summary: newSummary,
        recentTurns: state.recentTurns.slice(-RECENT_TURNS_KEEP)
      };
    }

    // Build context and call the model
    const messages = buildMessages(state, systemPrompt, message);
    const result = await env.AI.run("@cf/mistral/mistral-7b-instruct-v0.1", {
      messages,
      max_tokens: 512,
      temperature: 0.7
    }) as { response: string };

    const reply = result.response;

    // Persist updated state
    state.recentTurns.push(
      { role: "user", content: message, ts: Date.now() },
      { role: "assistant", content: reply, ts: Date.now() }
    );
    state.totalTurns += 2;

    await saveConversation(env.KV, state);

    return Response.json({
      reply,
      sessionStats: {
        totalTurns: state.totalTurns,
        recentTurns: state.recentTurns.length,
        hasSummary: !!state.summary,
        estimatedTokens: estimateTokens(messages)
      }
    });
  }
};
```

---

## Anti-patterns

- **Summarizing every request** — summarization costs one extra AI call; only trigger it when the window is truly full.
- **Discarding the old summary when summarizing again** — always pass the existing summary to the new summarization call so cumulative context is preserved.
- **Keeping all turns verbatim "just in case"** — this negates the compression benefit; trust the summary for older context.
- **Using a large, expensive model for summarization** — a 7B instruction model is sufficient; reserve the larger model for the actual reply.
- **Infinite session TTL in KV** — sessions accumulate; set a reasonable expiry (7 days) to avoid unbounded storage growth.

## Gotchas

- KV `get(..., "json")` returns `null` for missing keys — always handle the null case to create a fresh state.
- Workers AI `messages` must not be empty; if `recentTurns` is empty and there is no summary, the context will be just the system prompt and the new user message, which is fine.
- Summarization is async and adds ~500ms latency; if it fires mid-conversation, users notice a pause. Consider doing it on a trailing request or via a Queue.
- KV size limit is 25 MB per value; a summary + 10 verbatim turns should stay well under 100 KB — monitor with KV metrics.
- Session IDs must be user-scoped and opaque; never let a client pass an arbitrary session ID that could be another user's.

## Verification

```bash
# Start a conversation
for i in {1..25}; do
  curl -sX POST https://your-worker.workers.dev/chat \
    -H "Content-Type: application/json" \
    -d "{\"sessionId\":\"test-1\",\"message\":\"Turn $i: tell me something new.\"}" | jq .sessionStats
done
# After turn 20+, hasSummary should be true and recentTurns should cap at 10.

# Inspect stored state
wrangler kv key get "conv:test-1" --namespace-id YOUR_NAMESPACE_ID
```

## Related

- `llm-conversation-history-kv-rolling-window.md`
- `llm-conversation-history-d1-context-window-management.md`
- `llm-context-window-cloudflare-workers.md`
- `llm-prompt-compression-kv-cache-efficiency-workers.md`
- `rag-context-compression.md`

## Sources

- Workers KV: https://developers.cloudflare.com/kv/
- Workers AI text generation: https://developers.cloudflare.com/workers-ai/models/text-generation/
- Context window management patterns: https://www.anthropic.com/research/long-context
