# LLM Conversation History D1 Context Window Management

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A multi-turn chat application stores conversation history in KV or in-memory, then stuffs
the entire history into every LLM request. As conversations grow, you hit context limits,
token costs spike, and older messages crowd out system instructions. You need a persistent,
queryable history store with controlled context-window assembly that trims intelligently
without losing important context.

---

## Context

KV is a flat key-value store: you can append turns as a JSON blob, but you cannot query
by turn index, filter by role, or implement sliding-window or semantic retrieval strategies
without loading the entire history. D1 gives you SQL: per-turn rows, indexed by session
and position, queryable by recency or token budget.

**Design goals:**
- Never exceed the model's context limit (e.g. 8 192 tokens for most Workers AI models).
- Always include the system prompt and the most recent `N` turns.
- Optionally insert "anchor" turns (user-pinned important messages) regardless of age.
- Keep full history in D1 for audit, replay, and fine-tuning export — only the assembled
  context window is truncated.

---

## D1 Schema

```sql
-- schema.sql
CREATE TABLE IF NOT EXISTS conversations (
  session_id   TEXT NOT NULL,
  turn_index   INTEGER NOT NULL,
  role         TEXT NOT NULL CHECK(role IN ('system','user','assistant','tool')),
  content      TEXT NOT NULL,
  token_count  INTEGER NOT NULL DEFAULT 0,
  is_anchor    INTEGER NOT NULL DEFAULT 0,  -- 1 = always include
  created_at   TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (session_id, turn_index)
);

CREATE INDEX idx_conv_session_recent
  ON conversations (session_id, turn_index DESC);

-- Materialised token sum per session for fast budget checks
CREATE TABLE IF NOT EXISTS session_stats (
  session_id     TEXT PRIMARY KEY,
  total_turns    INTEGER NOT NULL DEFAULT 0,
  total_tokens   INTEGER NOT NULL DEFAULT 0,
  last_updated   TEXT NOT NULL DEFAULT (datetime('now'))
);
```

---

## Token Counting Helper

Use a simple whitespace-split estimator in Workers (no tiktoken available at edge); swap
for a real tokeniser if you add a pre-tokenisation step.

```typescript
// tokens.ts
export function estimateTokens(text: string): number {
  // ~0.75 words per token is a reasonable approximation for English prose.
  // Adjust per-model as needed.
  return Math.ceil(text.split(/\s+/).length / 0.75);
}
```

---

## Persisting Turns

```typescript
// history.ts
import { estimateTokens } from './tokens';

export interface Turn {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string;
  isAnchor?: boolean;
}

export async function appendTurn(
  db: D1Database,
  sessionId: string,
  turn: Turn
): Promise<number> {
  const tokens = estimateTokens(turn.content);

  // Get next index atomically via INSERT ... RETURNING or a prior SELECT
  const { results } = await db
    .prepare(
      `SELECT COALESCE(MAX(turn_index), -1) + 1 AS next_idx
       FROM conversations WHERE session_id = ?`
    )
    .bind(sessionId)
    .all<{ next_idx: number }>();

  const nextIdx = results[0].next_idx;

  await db.batch([
    db
      .prepare(
        `INSERT INTO conversations
           (session_id, turn_index, role, content, token_count, is_anchor)
         VALUES (?, ?, ?, ?, ?, ?)`
      )
      .bind(sessionId, nextIdx, turn.role, turn.content, tokens, turn.isAnchor ? 1 : 0),
    db
      .prepare(
        `INSERT INTO session_stats (session_id, total_turns, total_tokens, last_updated)
         VALUES (?, 1, ?, datetime('now'))
         ON CONFLICT(session_id) DO UPDATE SET
           total_turns  = total_turns + 1,
           total_tokens = total_tokens + excluded.total_tokens,
           last_updated = excluded.last_updated`
      )
      .bind(sessionId, tokens),
  ]);

  return nextIdx;
}
```

---

## Context Window Assembly

Fetch the most recent turns that fit within a token budget, always including anchors and
the system prompt.

```typescript
// context.ts
import { estimateTokens } from './tokens';

export interface ContextOptions {
  maxTokens?: number;      // default 6000 — leave headroom for response
  reserveForSystem?: number; // tokens reserved for system prompt
}

export async function assembleContext(
  db: D1Database,
  sessionId: string,
  systemPrompt: string,
  opts: ContextOptions = {}
): Promise<Array<{ role: string; content: string }>> {
  const maxTokens = opts.maxTokens ?? 6000;
  const systemTokens = estimateTokens(systemPrompt);
  let budget = maxTokens - systemTokens;

  // 1. Always fetch anchor turns
  const { results: anchors } = await db
    .prepare(
      `SELECT role, content, token_count, turn_index
       FROM conversations
       WHERE session_id = ? AND is_anchor = 1
       ORDER BY turn_index ASC`
    )
    .bind(sessionId)
    .all<{ role: string; content: string; token_count: number; turn_index: number }>();

  const anchorSet = new Set(anchors.map((a) => a.turn_index));
  budget -= anchors.reduce((s, a) => s + a.token_count, 0);

  // 2. Fetch recent turns (newest first) until budget exhausted
  const { results: recent } = await db
    .prepare(
      `SELECT role, content, token_count, turn_index
       FROM conversations
       WHERE session_id = ? AND is_anchor = 0
       ORDER BY turn_index DESC
       LIMIT 200`
    )
    .bind(sessionId)
    .all<{ role: string; content: string; token_count: number; turn_index: number }>();

  const included: typeof recent = [];
  for (const turn of recent) {
    if (budget <= 0) break;
    budget -= turn.token_count;
    included.push(turn);
  }

  // 3. Merge anchor + recent, preserve chronological order
  const merged = [...anchors, ...included.reverse()].sort(
    (a, b) => a.turn_index - b.turn_index
  );

  return [
    { role: 'system', content: systemPrompt },
    ...merged.map(({ role, content }) => ({ role, content })),
  ];
}
```

---

## Chat Handler

```typescript
// worker.ts
import { appendTurn } from './history';
import { assembleContext } from './context';

const SYSTEM_PROMPT =
  'You are a helpful assistant. Be concise. If uncertain, say so.';

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { sessionId, message } = await req.json<{
      sessionId: string;
      message: string;
    }>();

    // Persist user turn
    await appendTurn(env.DB, sessionId, { role: 'user', content: message });

    // Assemble context window
    const messages = await assembleContext(env.DB, sessionId, SYSTEM_PROMPT, {
      maxTokens: 6000,
    });

    // Call model
    const response = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
      messages,
      max_tokens: 512,
    });

    const assistantContent = response.response ?? '';

    // Persist assistant turn
    await appendTurn(env.DB, sessionId, {
      role: 'assistant',
      content: assistantContent,
    });

    return Response.json({ reply: assistantContent });
  },
};
```

---

## Session Pruning with Cron

Expire old sessions to keep D1 storage bounded.

```typescript
// scheduled.ts
export async function pruneOldSessions(db: D1Database, maxAgeDays = 90): Promise<void> {
  await db.batch([
    db.prepare(
      `DELETE FROM conversations
       WHERE session_id IN (
         SELECT session_id FROM session_stats
         WHERE last_updated < datetime('now', ? || ' days')
       )`
    ).bind(`-${maxAgeDays}`),
    db.prepare(
      `DELETE FROM session_stats
       WHERE last_updated < datetime('now', ? || ' days')`
    ).bind(`-${maxAgeDays}`),
  ]);
}
```

```toml
# wrangler.toml
[[triggers.crons]]
crons = ["0 3 * * *"]   # 03:00 UTC daily
```

---

## Anti-patterns

- **Storing full history in a KV blob** — forces loading the entire history on every turn to
  check length; no partial retrieval.
- **Truncating from the front without accounting for anchors** — drops context the user has
  flagged as important (e.g. the original task specification).
- **Using raw character count instead of token estimate** — a 3 000-character Chinese string
  may tokenise as 3 000 tokens; a 3 000-character English string is closer to 750.
- **Not persisting assistant turns** — if a Worker fails after the LLM responds but before
  writing to D1, history is inconsistent; use a Durable Object or Queues for transactional
  safety on critical paths.

---

## Gotchas

- D1's `batch()` is not a true ACID transaction across tables; for strict consistency,
  wrap operations in `db.prepare('BEGIN')` / `COMMIT` via the REST API or use a single
  combined statement.
- `assembleContext` performs two sequential D1 reads; if latency matters, collapse into one
  query using `ORDER BY is_anchor DESC, turn_index DESC` and split in application code.
- Workers AI context limits vary by model — verify `max_tokens` + assembled context does
  not exceed the model's total context length, not just the context you send.
- The `turn_index` gap-free assumption breaks if turns are deleted mid-session; use
  `ROW_NUMBER()` over `ORDER BY turn_index ASC` for display ordering if deletes are allowed.

---

## Verification

1. Create a session and insert 50 turns with known token counts; call `assembleContext`
   with `maxTokens: 1000` and confirm the returned slice fits within budget.
2. Mark turn 2 as an anchor; verify it appears in the assembled context even when all
   other turns from that era have been trimmed.
3. Run the cron handler against a seeded session older than `maxAgeDays`; confirm rows are
   removed from both tables.
4. Query `session_stats` and confirm `total_tokens` matches `SUM(token_count)` from
   `conversations` for the same `session_id`.

---

## Related

- `llm-conversation-history-kv-rolling-window.md`
- `llm-context-window-cloudflare-workers.md`
- `llm-context-window-management.md`
- `rag-context-compression.md`
- `workers-ai-durable-objects-stateful-sessions.md`

---

## Sources

- Cloudflare D1: https://developers.cloudflare.com/d1/
- Cloudflare Workers AI models and context limits: https://developers.cloudflare.com/workers-ai/models/
- Cloudflare Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
