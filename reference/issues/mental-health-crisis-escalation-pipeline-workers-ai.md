# Mental Health Crisis Escalation Pipeline with Workers AI

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A community platform needs to detect messages containing crisis indicators (self-harm, suicidal ideation) in real time, escalate high-confidence detections to a human moderation team within 60 seconds, preserve an auditable log in D1, and automatically purge message content after 24 hours to protect user privacy.

## Context

The pipeline has three layers:

1. **Classify** — every submitted message is run through a Workers AI text classification model (fine-tuned on crisis language) before it is written to the main database.
2. **Escalate** — detections above a confidence threshold are pushed into a Durable Object queue that enforces at-most-once Slack notification delivery.
3. **Log + Purge** — D1 stores `risk_score` and metadata; a nightly Cron Worker nullifies `message_snippet` rows older than 24 hours.

A feedback endpoint lets moderators mark escalations as false positives, feeding correction data back for future model fine-tuning.

## Classification and Escalation Worker

```typescript
import { Ai } from '@cloudflare/ai';

export interface Env {
  DB: D1Database;
  AI: Ai;
  ESCALATION_DO: DurableObjectNamespace;
  SLACK_WEBHOOK_URL: string; // via Workers secret
}

const RISK_THRESHOLD = 0.82;

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (req.method !== 'POST' || new URL(req.url).pathname !== '/message') {
      return new Response('not found', { status: 404 });
    }

    const { user_id, message } = await req.json<{ user_id: string; message: string }>();
    if (!user_id || typeof message !== 'string' || message.length > 4000) {
      return new Response('bad request', { status: 400 });
    }

    // 1. Classify the message
    const result = await (env.AI as any).run(
      '@cf/example-org/example-repo',
      { text: message },
    ) as { label: string; score: number }[];

    const crisisScore = result.find(r => r.label === 'crisis')?.score ?? 0;

    // 2. Log to D1 (snippet only — full message never stored)
    const detectionId = crypto.randomUUID();
    const snippet = message.slice(0, 120).replace(/[\r\n]+/g, ' ');
    await env.DB.prepare(`
      INSERT INTO crisis_detections
        (id, user_id, risk_score, message_snippet, detected_at, escalated, feedback)
      VALUES (?, ?, ?, ?, unixepoch(), ?, NULL)
    `).bind(
      detectionId, user_id, crisisScore,
      crisisScore >= RISK_THRESHOLD ? snippet : null,
      crisisScore >= RISK_THRESHOLD ? 1 : 0,
    ).run();

    // 3. Escalate via Durable Object if above threshold
    if (crisisScore >= RISK_THRESHOLD) {
      const doId = env.ESCALATION_DO.idFromName('global-queue');
      const stub = env.ESCALATION_DO.get(doId);
      ctx.waitUntil(
        stub.fetch('https://internal/enqueue', {
          method: 'POST',
          body: JSON.stringify({ detectionId, user_id, snippet, risk_score: crisisScore }),
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    }

    return Response.json({ ok: true, risk_score: crisisScore });
  },
};

// --- D1 schema (run once) ---
// CREATE TABLE IF NOT EXISTS crisis_detections (
//   id              TEXT PRIMARY KEY,
//   user_id         TEXT NOT NULL,
//   risk_score      REAL NOT NULL,
//   message_snippet TEXT,           -- nullified after 24h
//   detected_at     INTEGER NOT NULL,
//   escalated       INTEGER NOT NULL DEFAULT 0,
//   feedback        TEXT            -- 'true_positive' | 'false_positive' | NULL
// );
```

## Durable Object Escalation Queue

```typescript
export class EscalationQueue {
  private state: DurableObjectState;
  private env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async fetch(req: Request): Promise<Response> {
    const { detectionId, user_id, snippet, risk_score } =
      await req.json<{ detectionId: string; user_id: string; snippet: string; risk_score: number }>();

    // Idempotency: skip if already notified
    const already = await this.state.storage.get<boolean>(`notified:${detectionId}`);
    if (already) return Response.json({ ok: true, duplicate: true });

    await this.state.storage.put(`notified:${detectionId}`, true, { expirationTtl: 86400 });

    // Notify Slack within 60s
    const payload = {
      text: `:rotating_light: *Crisis alert* — risk score ${risk_score.toFixed(2)}`,
      blocks: [
        { type: 'section', text: { type: 'mrkdwn',
          text: `*User:* ${user_id}\n*Score:* ${risk_score.toFixed(3)}\n*Snippet:* ${snippet}` } },
        { type: 'actions', elements: [
          { type: 'button', text: { type: 'plain_text', text: 'Review' },
            url: `https://admin.example.com/crisis/${detectionId}` },
        ]},
      ],
    };

    const slackResp = await fetch(this.env.SLACK_WEBHOOK_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!slackResp.ok) {
      // Clear idempotency key so next invocation retries
      await this.state.storage.delete(`notified:${detectionId}`);
      return Response.json({ ok: false, status: slackResp.status }, { status: 500 });
    }

    return Response.json({ ok: true });
  }
}
```

## Nightly Content Purge Worker

```typescript
export default {
  async scheduled(_event: ScheduledEvent, env: Env) {
    const cutoff = Math.floor(Date.now() / 1000) - 86400; // 24h ago
    const result = await env.DB.prepare(`
      UPDATE crisis_detections
      SET    message_snippet = NULL
      WHERE  detected_at < ? AND message_snippet IS NOT NULL
    `).bind(cutoff).run();
    console.log(`Purged snippets from ${result.meta.changes} rows`);
  },
};
```

## False-Positive Feedback Endpoint

Moderators POST `{ detection_id, verdict: 'true_positive' | 'false_positive' }` to `/feedback`. The Worker updates the D1 row and, if `false_positive`, appends the detection ID to a KV list consumed by the model fine-tuning pipeline.

## Anti-patterns

- **Storing the full message text in D1** — store only a 120-character snippet for context; purge that after 24 h.
- **Sending Slack notifications from the Fetch handler synchronously** — this adds latency to the user-facing response; always use `waitUntil` + Durable Object.
- **Using a static threshold for all contexts** — crisis language varies by community; expose `RISK_THRESHOLD` as a Worker secret so it can be tuned without redeployment.
- **Skipping the feedback loop** — without labeled corrections, model accuracy degrades over time as language patterns shift.

## Gotchas

- The Durable Object idempotency TTL (`expirationTtl: 86400`) must exceed the maximum retry window of the caller to prevent re-notification.
- Workers AI custom models (`@cf/orchords/...`) require the model to be uploaded and activated in the Cloudflare dashboard before the binding resolves at runtime.
- The 60-second SLA to Slack is only achievable if the Durable Object and Slack webhook are in the same Cloudflare region or if Smart Placement is enabled.
- GDPR / CCPA: even the 120-character snippet may constitute personal data — confirm with legal whether the 24h retention window is sufficient for your jurisdiction.

## Verification

```bash
# Check recent high-risk detections
wrangler d1 execute example project-db --command \
  "SELECT id, user_id, risk_score, escalated, detected_at FROM crisis_detections WHERE risk_score >= 0.82 ORDER BY detected_at DESC LIMIT 20;"

# Confirm purge ran
wrangler d1 execute example project-db --command \
  "SELECT COUNT(*) AS remaining_snippets FROM crisis_detections WHERE message_snippet IS NOT NULL AND detected_at < unixepoch('now', '-1 day');"
```

## Related

- `self-harm-content-image-moderation-workers-ai.md`
- `platform-manipulation-sock-puppet-detection-d1.md`
- Cloudflare Durable Objects — at-most-once delivery patterns

## Sources

- Cloudflare Workers AI: https://developers.cloudflare.com/workers-ai/
- Cloudflare Durable Objects: https://developers.cloudflare.com/durable-objects/
- Crisis Text Line engineering blog — ML model deployment for crisis detection
- SAMHSA Safe Messaging Guidelines: https://www.samhsa.gov/
