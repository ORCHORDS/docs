# llm-context-window-cloudflare-workers

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

example project conversation history grows until the Worker throws
`context length exceeded` (or silently truncates). Long
threads cause CPU time to spike near the 30-second limit
as the serialisation loop concatenates thousands of rows from
D1. On mobile, streaming responses stall mid-generation when
the radio switches from LTE to WiFi, leaving the user with
a broken partial reply and no recovery.

## Context

example project supports short multi-turn conversations on anonymous
posts (replies, clarifications). Conversation history is stored
in D1. Workers process each turn synchronously: fetch history,
build context, call `env.AI.run`, stream back to the mobile
client. Workers have a 128 MB memory cap and CPU limits that
vary by plan (10 ms / 30 s wall-clock on Workers Free/Paid).

## 1. Workers Runtime Limits Relevant to LLM Calls

```
Limit                    Workers Free   Workers Paid (Unbound)
-----------------------  ------------   ----------------------
CPU time per request     10 ms          30 s
Wall-clock time          30 s           No limit (I/O OK)
Memory                   128 MB         128 MB
Subrequests              50             1000
env.AI.run (awaited)     Counts as I/O  Counts as I/O (no CPU)
D1 query (awaited)       Counts as I/O  Counts as I/O (no CPU)
```

`env.AI.run` and D1 queries are async I/O — they do not burn
CPU time while awaiting. The 30 s CPU limit applies only to
synchronous JS execution. Token counting/serialisation loops
DO burn CPU; keep them under 5 ms per request.

## 2. Context Window Limits by Model

```
Model                             Context window  Notes
--------------------------------  --------------  ------------------
@cf/meta/llama-3.3-70b-fp8-fast  128 k tokens    example project flagship
@cf/meta/llama-3.1-8b-instruct   128 k tokens    Moderation/fast path
@cf/mistral/mistral-7b-instruct   32 k tokens    Legacy, avoid
@cf/qwen/qwen2.5-coder-32b        32 k tokens    Code tasks
```

128 k tokens ≈ 96 k words ≈ ~600 average posts. In practice,
set a hard limit at 32 k tokens for conversation history to
keep inference latency under 1 s on the mobile critical path.

## 3. Chunking Strategies for D1 History

Fetch only the last N turns; avoid full-table scans:

```typescript
const MAX_HISTORY_TURNS = 20;   // configurable per post type
const MAX_PROMPT_TOKENS = 6000; // leave room for system + output

async function buildContext(
  postId: string,
  env: Env,
): Promise<{ messages: ChatMessage[]; truncated: boolean }> {
  const rows = await env.DB.prepare(
    "SELECT role, content, token_count " +
    "FROM messages WHERE post_id = ? " +
    "ORDER BY created_at DESC LIMIT ?"
  ).bind(postId, MAX_HISTORY_TURNS).all<MessageRow>();

  const turns  = rows.results.reverse();
  const output: ChatMessage[] = [];
  let   tokens = 0;
  let   truncated = false;

  for (const t of turns) {
    if (tokens + t.token_count > MAX_PROMPT_TOKENS) {
      truncated = true;
      break;
    }
    output.push({ role: t.role, content: t.content });
    tokens += t.token_count;
  }

  return { messages: output, truncated };
}
```

Store `token_count` at write time using a simple heuristic
(chars / 4) to avoid tokeniser overhead per request.

## 4. D1 Schema for Conversation History

```sql
CREATE TABLE messages (
  id          TEXT PRIMARY KEY,
  post_id     TEXT NOT NULL,
  role        TEXT NOT NULL,   -- 'user' | 'assistant' | 'system'
  content     TEXT NOT NULL,
  token_count INTEGER NOT NULL DEFAULT 0,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_msgs_post_time ON messages(post_id, created_at);

-- Summarisation queue entry (see section 5)
CREATE TABLE context_summaries (
  post_id       TEXT PRIMARY KEY,
  summary       TEXT NOT NULL,
  covered_until INTEGER NOT NULL,   -- unixepoch of last msg in summary
  token_count   INTEGER NOT NULL,
  updated_at    INTEGER NOT NULL DEFAULT (unixepoch())
);
```

D1 global read replicas serve history reads close to the user's
mobile PoP; writes (new turns) go to the primary.

## 5. Summarisation to Manage Growing History

When `truncated = true`, run a background summarisation turn
via a Queue to compress old history. Inject the summary as a
`system` message prefix at inference time:

```typescript
async function fetchContextWithSummary(
  postId: string,
  env: Env,
): Promise<ChatMessage[]> {
  const [summaryRow, recent] = await Promise.all([
    env.DB.prepare(
      "SELECT summary FROM context_summaries WHERE post_id = ?"
    ).bind(postId).first<{ summary: string }>(),
    buildContext(postId, env),
  ]);

  const messages: ChatMessage[] = [];
  if (summaryRow) {
    messages.push({
      role: "system",
      content: `Previous conversation summary: ${summaryRow.summary}`,
    });
  }
  messages.push(...recent.messages);
  return messages;
}
```

Summarisation Worker (runs off the critical path via Queue):

```typescript
async function summarise(postId: string, env: Env) {
  const { messages } = await buildContext(postId, env);
  const summary = await env.AI.run(
    "@cf/meta/llama-3.1-8b-instruct",
    {
      messages: [
        { role: "system",
          content: "Summarise this conversation in 3 sentences." },
        ...messages,
      ],
      max_tokens: 120,
    },
  );
  await env.DB.prepare(
    "INSERT OR REPLACE INTO context_summaries " +
    "(post_id, summary, covered_until, token_count, updated_at) " +
    "VALUES (?, ?, unixepoch(), ?, unixepoch())"
  ).bind(postId, summary.response, 120).run();
}
```

## 6. Streaming Responses to Mobile Clients

Return a `ReadableStream` directly; do not buffer:

```typescript
async function streamReply(
  messages: ChatMessage[],
  env: Env,
): Promise<Response> {
  const stream = await env.AI.run(
    "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    { messages, stream: true, max_tokens: 512 },
  );

  let seq = 0;
  const transformed = (stream as ReadableStream)
    .pipeThrough(new TransformStream({
      transform(chunk, ctrl) {
        // Inject SSE id for mobile reconnect resume
        const text = new TextDecoder().decode(chunk);
        ctrl.enqueue(
          new TextEncoder().encode(`id: ${seq++}\n${text}`)
        );
      },
    }));

  return new Response(transformed, {
    headers: {
      "Content-Type":      "text/event-stream",
      "Cache-Control":     "no-cache",
      "X-Accel-Buffering": "no",
      "retry":             "3000",
    },
  });
}
```

Mobile clients use `Last-Event-ID` to resume from the last
received sequence ID if the radio drops mid-stream.

## Anti-patterns

- Fetching all history rows then iterating in JS to count
  tokens — O(n) CPU on every request; store `token_count`
  at write time instead.
- Using `JSON.stringify(allHistory)` to size the context —
  string length ≠ token count; off by 3-5× for CJK content.
- Wrapping `env.AI.run` stream in `Response.json()` — buffers
  the entire generation before the mobile client receives data.
- Storing summaries in KV instead of D1 — KV is eventually
  consistent; stale summaries cause context jumps mid-thread.
- Running summarisation on the request critical path — adds
  800 ms-2 s; always offload to a Queue consumer.

## Gotchas

- Workers `cpu time` limit applies to JS execution only; long
  `await env.AI.run(...)` calls do not consume the 30 s budget
  while waiting, but DO consume wall-clock time.
- 128 MB memory cap is per isolate, not per request; if the
  Worker handles multiple concurrent requests, conversation
  history arrays from all requests share that pool.
- iOS Safari closes the SSE connection after 30 s of no data
  even with `retry: 3000`; send a `ping` SSE comment every
  15 s to keep the connection alive: `: ping\n\n`.
- `token_count = chars / 4` underestimates for code snippets
  and emoji by up to 30%; add a 20% safety margin on the
  truncation threshold.
- D1 `covered_until` in `context_summaries` must be compared
  against the newest message timestamp to detect stale summaries
  after a new conversation turn.

## Verification

```bash
# 1. Confirm context build stays under 5 ms CPU
wrangler tail --format=json | \
  jq 'select(.logs[].message | test("context_build_ms")) |
      .logs[].message'

# 2. Confirm streaming tokens arrive incrementally (not batched)
curl -N -X POST https://example project.example.com/api/chat \
  -H "Content-Type: application/json" \
  -d '{"postId":"abc","message":"explain the rules"}' \
  --no-buffer | head -40

# 3. Confirm truncation triggers summarisation queue entry
wrangler d1 execute example project_DB \
  --command "SELECT post_id, updated_at FROM context_summaries
             ORDER BY updated_at DESC LIMIT 5"
```

## Related

- `cloudflare/workers-resource-limits.md`
- `cloudflare/workers-ai-mobile-inference-latency.md`
- `cloudflare/d1-read-replicas-mobile-api-latency.md`
- `cloudflare/queues-batch-processing.md`
- `ai-ml/llm-context-window-management.md`

## Source URLs (verified 2026-08-22)

- https://developers.cloudflare.com/workers/platform/limits/
- https://developers.cloudflare.com/workers-ai/models/
- https://developers.cloudflare.com/workers-ai/configuration/
- https://developers.cloudflare.com/d1/platform/limits/
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/agents/api-reference/http-sse/
