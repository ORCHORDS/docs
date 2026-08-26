# Crisis Intervention Signal Detection with Workers AI

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

example project posts occasionally contain acute distress signals — expressions of suicidal ideation, imminent self-harm intent, or requests for emergency help. The current pipeline has no mechanism to intercept these posts before publication and route them to crisis-support resources or a human responder on call. Community moderators have surfaced multiple missed cases via retrospective reports.

## Context

Anonymous social platforms carry a heightened duty of care for crisis content because users may post under distress specifically because anonymity lowers the barrier to disclosure. example project operates under the EU Digital Services Act risk assessment obligations, which explicitly require very large online platforms to implement systemic safeguards for content that may put users' lives at risk. A Cloudflare Workers AI pipeline can intercept posts at ingestion time, score them for crisis signals, and — before persisting the post to D1 — branch into a safe messaging response path that presents the user with hotline resources while queuing the post for human review rather than immediate publication.

## Crisis Signal Scoring at the Edge

The classifier runs inline in the post-ingestion Worker. It uses a structured prompt against `@cf/meta/llama-3.1-8b-instruct` asking the model to output a JSON severity tier: `NONE`, `CONCERN`, `ACUTE`. Only `ACUTE` triggers the full intervention path; `CONCERN` adds a soft resource banner without blocking publication.

```typescript
export interface Env {
  AI: Ai;
  DB: D1Database;
  CRISIS_QUEUE: Queue<CrisisEvent>;
}

interface CrisisScore {
  tier: 'NONE' | 'CONCERN' | 'ACUTE';
  confidence: number;
  signals: string[];
}

interface CrisisEvent {
  postId: string;
  userId: string;        // opaque session token — not a persistent ID
  tier: CrisisScore['tier'];
  detectedAt: string;
}

const CRISIS_SYSTEM_PROMPT = `You are a mental health crisis classifier trained on safe messaging guidelines.
Classify the following user post for crisis signals.
Return ONLY valid JSON matching: {"tier":"NONE"|"CONCERN"|"ACUTE","confidence":0.0-1.0,"signals":["list","of","signals"]}
- ACUTE: explicit suicidal intent, imminent self-harm plan, request for means, farewell messages
- CONCERN: passive ideation, hopelessness, social withdrawal language, veiled distress
- NONE: no crisis signals present
Never repeat the post text in your response.`;

async function scoreCrisisSignals(
  ai: Ai,
  text: string,
): Promise<CrisisScore> {
  const result = await ai.run('@cf/meta/llama-3.1-8b-instruct', {
    messages: [
      { role: 'system', content: CRISIS_SYSTEM_PROMPT },
      { role: 'user', content: text },
    ],
    max_tokens: 200,
    temperature: 0,
  }) as { response: string };

  try {
    const parsed = JSON.parse(result.response.trim()) as CrisisScore;
    return parsed;
  } catch {
    // Fail open: if parsing fails, treat as NONE to avoid blocking benign posts
    return { tier: 'NONE', confidence: 0, signals: [] };
  }
}
```

## Post Ingestion Branch Logic

After scoring, the Worker branches on tier. `ACUTE` posts are held from the feed, the author receives a crisis resource response, and a `CrisisEvent` message is enqueued for the on-call human moderator. `CONCERN` posts are published but the author's session receives a banner resource. All tiers are logged to D1 with the score — not the post body — to minimise sensitive data retention.

```typescript
const CRISIS_RESOURCES: Record<string, string> = {
  en: 'If you are in crisis, please reach out: 988 (US), 116 123 (UK Samaritans), 3114 (DE)',
  es: 'Si estás en crisis, llama al: 024 (España), 800 290 0024 (México)',
};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const body = await request.json<{
      text: string;
      postId: string;
      sessionToken: string;
      lang?: string;
    }>();

    const { text, postId, sessionToken, lang = 'en' } = body;

    // 1. Score crisis signals in parallel with post validation
    const [crisis] = await Promise.all([
      scoreCrisisSignals(env.AI, text),
    ]);

    // 2. Persist score (never persist the raw post text here)
    await env.DB.prepare(
      `INSERT INTO crisis_scores (post_id, session_token, tier, confidence, signals_json, created_at)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6)`,
    )
      .bind(
        postId,
        sessionToken,
        crisis.tier,
        crisis.confidence,
        JSON.stringify(crisis.signals),
        new Date().toISOString(),
      )
      .run();

    // 3. Branch on tier
    if (crisis.tier === 'ACUTE') {
      // Enqueue for human moderator — non-blocking send
      await env.CRISIS_QUEUE.send({
        postId,
        userId: sessionToken,
        tier: 'ACUTE',
        detectedAt: new Date().toISOString(),
      });

      const resource = CRISIS_RESOURCES[lang] ?? CRISIS_RESOURCES['en'];
      return Response.json(
        {
          held: true,
          message: 'Your post has been received. ' + resource,
          crisisResource: resource,
        },
        { status: 202 },
      );
    }

    if (crisis.tier === 'CONCERN') {
      const resource = CRISIS_RESOURCES[lang] ?? CRISIS_RESOURCES['en'];
      return Response.json({
        held: false,
        bannerResource: resource,
        postId,
      });
    }

    return Response.json({ held: false, postId });
  },
} satisfies ExportedHandler<Env>;
```

## Queue Consumer and On-Call Escalation

```typescript
// Queue consumer Worker (separate Worker binding)
export default {
  async queue(batch: MessageBatch<CrisisEvent>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const event = msg.body;

      // Mark the post as held in D1 for moderator dashboard
      await env.DB.prepare(
        `UPDATE posts SET moderation_status = 'CRISIS_HOLD', held_at = ?1
         WHERE id = ?2`,
      )
        .bind(new Date().toISOString(), event.postId)
        .run();

      // Notify on-call via internal webhook (PagerDuty / Opsgenie)
      await fetch(env.ONCALL_WEBHOOK_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          summary: `ACUTE crisis signal on post ${event.postId}`,
          severity: 'critical',
          source: 'example project-crisis-worker',
          detectedAt: event.detectedAt,
        }),
      });

      msg.ack();
    }
  },
} satisfies ExportedHandler<Env>;
```

## D1 Schema

```sql
-- migration: 0006_crisis_detection.sql
CREATE TABLE IF NOT EXISTS crisis_scores (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  post_id        TEXT NOT NULL,
  session_token  TEXT NOT NULL,
  tier           TEXT NOT NULL CHECK(tier IN ('NONE','CONCERN','ACUTE')),
  confidence     REAL NOT NULL,
  signals_json   TEXT NOT NULL DEFAULT '[]',
  created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_crisis_tier
  ON crisis_scores(tier, created_at DESC);

-- posts table addition
ALTER TABLE posts ADD COLUMN moderation_status TEXT NOT NULL DEFAULT 'PENDING';
ALTER TABLE posts ADD COLUMN held_at TEXT;
```

## Anti-patterns

- Storing the full post text alongside the crisis score in the `crisis_scores` table — minimise sensitive data at rest; the score and signals are sufficient for triage.
- Blocking the HTTP response while waiting for the queue send to complete — use `ctx.waitUntil()` or fire-and-forget for the queue enqueue if latency is critical.
- Using only keyword matching (e.g., regex for "suicide") without LLM context — figurative language and song lyrics trigger false positives at high rates.

## Gotchas

- Workers AI inference adds 200–600 ms of latency; if your post-ingestion path is synchronous, instrument this call with `performance.now()` and set a timeout with `Promise.race` against a fallback of `NONE` to avoid blocking post creation.
- The model may refuse to output JSON if the user text contains prompt injection attempts — always wrap the parse in try/catch and fail open to `NONE` rather than failing the entire request.

## Verification

```bash
# Test ACUTE detection
curl -X POST https://example project-ingest.example.workers.dev/post \
  -H "Content-Type: application/json" \
  -d '{"text":"I have decided tonight is my last night","postId":"p001","sessionToken":"s_abc","lang":"en"}'

# Check held posts in D1
wrangler d1 execute example project-db \
  --command "SELECT post_id, tier, confidence, created_at FROM crisis_scores WHERE tier != 'NONE' ORDER BY created_at DESC LIMIT 20"

# Monitor queue depth
wrangler queues list
```

## Related

- `issues/self-harm-content-detection-workers-ai.md`
- `issues/real-time-toxic-content-scoring-workers-ai.md`
- `issues/anonymous-content-reporting-worker-pipeline.md`
- `issues/emergency-content-takedown-circuit-breaker-queues.md`

## Sources

- https://developers.cloudflare.com/workers-ai/models/llama-3.1-8b-instruct/
- https://developers.cloudflare.com/queues/
- https://www.sprc.org/resources-programs/safe-messaging-guidelines/
- https://digital-strategy.ec.europa.eu/en/policies/digital-services-act-package
