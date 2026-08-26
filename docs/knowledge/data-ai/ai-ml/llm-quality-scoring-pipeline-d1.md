# LLM Response Quality Scoring Pipeline with D1
- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You are running an LLM feature in production (answer bot, summariser, code
assistant) and have no systematic signal on output quality beyond user
thumbs-up/down. You need an automated quality scoring pipeline that evaluates
each response — for accuracy, relevance, and fluency — logs scores to D1, and
surfaces regressions when a model is swapped or a prompt is changed.

## Context

"LLM-as-judge" uses a capable LLM to evaluate the output of a smaller or cheaper
LLM. This pattern runs entirely inside Workers:

- **Generator Worker** — produces the LLM response and enqueues an evaluation
  job in a Queue.
- **Evaluator Worker** — consumes the Queue, calls the judge model, writes scores
  to D1.
- **Dashboard query** — D1 aggregations surface P50/P95 quality scores and
  per-prompt-version trends.

Using a Queue decouples evaluation latency from user-facing latency: the user
gets the response immediately; scoring happens asynchronously.

---

## Section 1 — D1 Schema

```sql
-- migrations/0001_quality_scoring.sql

CREATE TABLE IF NOT EXISTS llm_responses (
  id            TEXT PRIMARY KEY,          -- UUID
  prompt_hash   TEXT NOT NULL,             -- SHA-256 of the prompt template
  prompt_ver    TEXT NOT NULL,             -- e.g. "v3.2"
  model         TEXT NOT NULL,
  user_query    TEXT NOT NULL,
  response_text TEXT NOT NULL,
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS quality_scores (
  id              TEXT PRIMARY KEY,
  response_id     TEXT NOT NULL REFERENCES llm_responses(id),
  relevance       REAL NOT NULL CHECK (relevance BETWEEN 0 AND 1),
  accuracy        REAL NOT NULL CHECK (accuracy  BETWEEN 0 AND 1),
  fluency         REAL NOT NULL CHECK (fluency   BETWEEN 0 AND 1),
  composite       REAL NOT NULL,           -- weighted average
  judge_model     TEXT NOT NULL,
  judge_reasoning TEXT,
  scored_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_quality_prompt_ver  ON quality_scores(scored_at, composite);
CREATE INDEX idx_quality_response_id ON quality_scores(response_id);
```

---

## Section 2 — Generator Worker: Capture and Enqueue

```typescript
// workers/generator/index.ts
import { v4 as uuidv4 } from "uuid";
import { sha256Hex }     from "./util";

export interface Env {
  AI:    Ai;
  DB:    D1Database;
  QUEUE: Queue;
}

const PROMPT_VERSION = "v3.2";
const MODEL          = "@cf/meta/llama-3.1-8b-instruct";

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { query, context } = await req.json<{ query: string; context?: string }>();

    const systemPrompt = buildSystemPrompt(context);
    const messages: RoleScopedChatInput[] = [
      { role: "system",  content: systemPrompt },
      { role: "user",    content: query },
    ];

    // Detect mobile for concise responses
    const ua       = req.headers.get("User-Agent") ?? "";
    const isMobile = /Mobile|Android|iPhone|iPad/.test(ua);

    const aiResponse = await env.AI.run(MODEL, {
      messages,
      max_tokens: isMobile ? 300 : 800,
      stream:     false,
    });

    const responseText = (aiResponse as any).response ?? "";
    const responseId   = uuidv4();
    const promptHash   = await sha256Hex(systemPrompt);

    // Persist the response for reference by the evaluator
    await env.DB.prepare(
      `INSERT INTO llm_responses (id, prompt_hash, prompt_ver, model, user_query, response_text)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6)`,
    )
      .bind(responseId, promptHash, PROMPT_VERSION, MODEL, query, responseText)
      .run();

    // Enqueue async evaluation — non-blocking
    await env.QUEUE.send({
      responseId,
      userQuery:    query,
      responseText,
      promptVer:    PROMPT_VERSION,
      isMobile,
    });

    return Response.json({ id: responseId, text: responseText });
  },
};

function buildSystemPrompt(context?: string): string {
  const base = "You are a helpful assistant. Answer accurately and concisely.";
  return context ? `${base}\n\nContext:\n${context}` : base;
}
```

```typescript
// workers/generator/util.ts
export async function sha256Hex(input: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(input));
  return Array.from(new Uint8Array(buf))
    .map(b => b.toString(16).padStart(2, "0"))
    .join("");
}
```

---

## Section 3 — Evaluator Worker: Judge Model Scoring

```typescript
// workers/evaluator/index.ts
import { v4 as uuidv4 } from "uuid";

export interface Env {
  AI: Ai;
  DB: D1Database;
}

interface QueueMessage {
  responseId:   string;
  userQuery:    string;
  responseText: string;
  promptVer:    string;
  isMobile:     boolean;
}

const JUDGE_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast";

export default {
  async queue(batch: MessageBatch<QueueMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await scoreResponse(env, msg.body);
        msg.ack();
      } catch (err) {
        console.error("Scoring failed", msg.body.responseId, err);
        msg.retry({ delaySeconds: 30 });
      }
    }
  },
};

async function scoreResponse(env: Env, job: QueueMessage): Promise<void> {
  const judgePrompt = buildJudgePrompt(job.userQuery, job.responseText, job.isMobile);

  const judgeResponse = await env.AI.run(JUDGE_MODEL, {
    messages: [{ role: "user", content: judgePrompt }],
    max_tokens: job.isMobile ? 120 : 300,
    stream: false,
  });

  const raw = (judgeResponse as any).response ?? "";
  const scores = parseJudgeOutput(raw);

  const composite = scores.relevance * 0.4 + scores.accuracy * 0.4 + scores.fluency * 0.2;

  await env.DB.prepare(
    `INSERT INTO quality_scores
       (id, response_id, relevance, accuracy, fluency, composite, judge_model, judge_reasoning)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)`,
  )
    .bind(
      uuidv4(),
      job.responseId,
      scores.relevance,
      scores.accuracy,
      scores.fluency,
      composite,
      JUDGE_MODEL,
      scores.reasoning ?? null,
    )
    .run();
}

function buildJudgePrompt(query: string, response: string, isMobile: boolean): string {
  const reasoningInstruction = isMobile
    ? "Omit the reasoning field."
    : `"reasoning": "<one sentence explaining the scores>"`;

  return `You are a strict LLM output evaluator.

User query: ${query}

LLM response:
${response}

Rate the response on three dimensions (each 0.0–1.0):
- relevance: Does it directly address the query?
- accuracy:  Is the factual content correct and unambiguous?
- fluency:   Is the language clear and well-formed?

Reply ONLY with valid JSON:
{"relevance": <float>, "accuracy": <float>, "fluency": <float>, ${reasoningInstruction}}`;
}

interface JudgeScores {
  relevance: number;
  accuracy:  number;
  fluency:   number;
  reasoning?: string;
}

function parseJudgeOutput(raw: string): JudgeScores {
  const match = raw.match(/\{[\s\S]*\}/);
  if (!match) return { relevance: 0.5, accuracy: 0.5, fluency: 0.5 };

  try {
    const parsed = JSON.parse(match[0]);
    return {
      relevance: clamp(Number(parsed.relevance), 0, 1),
      accuracy:  clamp(Number(parsed.accuracy),  0, 1),
      fluency:   clamp(Number(parsed.fluency),   0, 1),
      reasoning: typeof parsed.reasoning === "string" ? parsed.reasoning : undefined,
    };
  } catch {
    return { relevance: 0.5, accuracy: 0.5, fluency: 0.5 };
  }
}

function clamp(v: number, min: number, max: number): number {
  return Number.isFinite(v) ? Math.min(max, Math.max(min, v)) : min;
}
```

---

## Section 4 — Querying Quality Trends and Alerting

```typescript
// workers/dashboard/queries.ts
export async function getQualityTrend(
  db: D1Database,
  promptVer?: string,
  days = 7,
): Promise<QualityTrendRow[]> {
  return (
    await db
      .prepare(
        `SELECT
           date(qs.scored_at) AS day,
           r.prompt_ver,
           COUNT(*)           AS sample_count,
           AVG(qs.relevance)  AS avg_relevance,
           AVG(qs.accuracy)   AS avg_accuracy,
           AVG(qs.composite)  AS avg_composite
         FROM quality_scores qs
         JOIN llm_responses r ON qs.response_id = r.id
         WHERE qs.scored_at >= datetime('now', '-' || ?1 || ' days')
           AND (?2 IS NULL OR r.prompt_ver = ?2)
         GROUP BY day, r.prompt_ver
         ORDER BY day DESC`,
      )
      .bind(days, promptVer ?? null)
      .all<QualityTrendRow>()
  ).results;
}

export interface QualityTrendRow {
  day:            string;
  prompt_ver:     string;
  sample_count:   number;
  avg_relevance:  number;
  avg_accuracy:   number;
  avg_composite:  number;
}

// Alert if composite drops below threshold for a prompt version
export async function detectRegression(
  db: D1Database,
  promptVer: string,
  threshold = 0.70,
  windowHours = 1,
): Promise<boolean> {
  const row = await db
    .prepare(
      `SELECT AVG(qs.composite) AS avg_composite
         FROM quality_scores qs
         JOIN llm_responses r ON qs.response_id = r.id
        WHERE r.prompt_ver = ?1
          AND qs.scored_at >= datetime('now', '-' || ?2 || ' hours')`,
    )
    .bind(promptVer, windowHours)
    .first<{ avg_composite: number | null }>();

  if (!row || row.avg_composite === null) return false;
  return row.avg_composite < threshold;
}
```

Wire `detectRegression` into a cron handler to push an alert when quality drops:

```typescript
// workers/dashboard/index.ts  — cron trigger
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const regressed = await detectRegression(env.DB, "v3.2", 0.70, 1);
    if (regressed) {
      await env.ALERT_QUEUE.send({ type: "quality_regression", promptVer: "v3.2" });
    }
  },
};
```

Wrangler config for the cron:

```toml
[triggers]
crons = ["*/15 * * * *"]  # every 15 minutes
```

---

## Anti-patterns

- **Blocking user response on scoring** — the judge model call takes 1–3 s; running
  it synchronously before returning the response to the user makes the UI feel slow.
  Always use a Queue.
- **Using the same model as generator and judge** — a model cannot reliably score
  its own output. Use a more capable judge (e.g., score Llama-3.1-8B outputs with
  Llama-3.3-70B).
- **No JSON parse guard on judge output** — judge models sometimes emit explanation
  text before or after the JSON. Always extract with a regex rather than
  `JSON.parse(raw)` directly.
- **Scoring every single response** — at high volume this creates D1 write pressure
  and judge cost. Sample at 10–20 % for healthy baselines; score 100 % only when
  a prompt version changes.
- **Storing raw judge reasoning on every mobile-originated call** — reasoning text
  is debugging data, not user-facing. Omit it on mobile via the `isMobile` flag to
  save D1 bytes and judge tokens.

---

## Gotchas

- Workers Queues deliver messages at-least-once; the evaluator must be idempotent.
  A simple guard: check if `quality_scores` already has a row for `response_id`
  before inserting.
- D1 `AVG()` returns `null` for empty result sets. Always handle `null` in the
  regression check rather than comparing with `< threshold` directly.
- `crypto.randomUUID()` is available natively in Workers — no need for the `uuid`
  package. Replace `uuidv4()` with `crypto.randomUUID()` to keep the bundle lean.
- Judge models are rate-limited independently of generator models in AI Gateway.
  Set a separate project in AI Gateway for the evaluator path so generator traffic
  does not starve the judge.
- The `scored_at` column uses SQLite `datetime('now')` which is UTC. All trend
  queries should also use UTC comparisons; avoid mixing local-time strings.

---

## Verification

```bash
# Confirm data is flowing after a few test calls:
wrangler d1 execute your-db --command \
  "SELECT prompt_ver, COUNT(*), AVG(composite) FROM quality_scores
     JOIN llm_responses ON quality_scores.response_id = llm_responses.id
   GROUP BY prompt_ver
   ORDER BY scored_at DESC LIMIT 10;"

# Regression check over last hour:
wrangler d1 execute your-db --command \
  "SELECT AVG(composite) FROM quality_scores
   WHERE scored_at >= datetime('now', '-1 hours');"
```

Unit test for parse robustness:

```typescript
import { expect, test } from "vitest";

test("parseJudgeOutput handles fenced JSON", () => {
  const raw = "Sure! Here are the scores:\n```json\n{\"relevance\":0.9,\"accuracy\":0.8,\"fluency\":0.95}\n```";
  // parseJudgeOutput is exported for testing
  const scores = parseJudgeOutput(raw);
  expect(scores.relevance).toBeCloseTo(0.9);
  expect(scores.accuracy).toBeCloseTo(0.8);
});
```

---

## Related

- `llm-as-judge-trace-evaluation.md` — judge model patterns for trace-level eval
- `llm-eval-harness-ci-regression.md` — CI-time regression testing
- `ai-cost-monitoring.md` — tracking spend alongside quality
- `agent-evaluation-patterns.md` — evaluating multi-step agents
- `llm-ab-testing.md` — A/B testing prompt versions

---

## Sources

- Cloudflare Queues Workers integration: https://developers.cloudflare.com/queues/reference/javascript-apis/
- D1 query API: https://developers.cloudflare.com/d1/worker-api/
- LLM-as-Judge survey: https://arxiv.org/abs/2306.05685
- Workers AI model catalogue: https://developers.cloudflare.com/workers-ai/models/
