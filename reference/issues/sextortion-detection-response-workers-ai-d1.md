# Sextortion Detection and Response — Workers AI + D1

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Anonymous users on example project receive private messages containing coercive demands backed by threats to publish intimate images unless payment or further images are provided. The platform must detect these patterns in real time and trigger victim-support escalation without breaking sender anonymity for false positives.

## Context

example project direct messaging runs through Cloudflare Workers with message bodies stored transiently in KV (TTL 7 days) and conversation metadata indexed in D1. Because accounts are anonymous, sextortion often originates from newly registered ephemeral sessions. Workers AI text classification can score each outbound message before delivery; Durable Objects gate delivery on the score; D1 persists threat evidence for potential law-enforcement holds.

## Detection — Workers AI Classifier

```typescript
// workers/sextortion-detector.ts
import { Ai } from "@cloudflare/ai";

interface Env {
  AI: Ai;
  DB: D1Database;
  MESSAGE_KV: KVNamespace;
  THREAT_QUEUE: Queue;
}

interface SextortionSignal {
  hasPaymentDemand: boolean;
  hasImageThreat: boolean;
  hasCounting: boolean;       // "you have 24 hours"
  hasPersonalData: boolean;   // name / location mention
  score: number;
}

const SEXTORTION_PROMPT = `
You are a trust-and-safety classifier. Analyse the message below for sextortion signals:
coercive payment demands, threats to share intimate images, countdown ultimatums,
references to personal identifiers. Return JSON with fields:
hasPaymentDemand (bool), hasImageThreat (bool), hasCounting (bool),
hasPersonalData (bool), score (0.0–1.0), reasoning (string ≤ 80 chars).
Message: `;

export async function classifyMessage(
  text: string,
  env: Env
): Promise<SextortionSignal> {
  const ai = new Ai(env.AI);
  const response = await ai.run("@cf/meta/llama-3.1-8b-instruct", {
    prompt: SEXTORTION_PROMPT + JSON.stringify(text),
    max_tokens: 200,
  });

  try {
    const raw = (response as { response: string }).response;
    const json = raw.slice(raw.indexOf("{"), raw.lastIndexOf("}") + 1);
    return JSON.parse(json) as SextortionSignal;
  } catch {
    return {
      hasPaymentDemand: false,
      hasImageThreat: false,
      hasCounting: false,
      hasPersonalData: false,
      score: 0,
    };
  }
}

// Keyword pre-filter to save AI tokens on obvious misses
const FAST_PATTERN =
  /\b(bitcoin|crypto|venmo|paypal|zelle|onlyfans|leak|expose|naked|nude|screenshot|24.hours|48.hours|forward.to.everyone)\b/i;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const { senderId, recipientId, messageId, body } = await request.json<{
      senderId: string;
      recipientId: string;
      messageId: string;
      body: string;
    }>();

    // Fast path: no suspicious tokens → allow
    if (!FAST_PATTERN.test(body)) {
      return new Response(JSON.stringify({ action: "allow" }), { status: 200 });
    }

    const signal = await classifyMessage(body, env);

    await env.DB.prepare(
      `INSERT OR IGNORE INTO sextortion_signals
         (message_id, sender_id, recipient_id, score,
          has_payment_demand, has_image_threat, has_counting,
          has_personal_data, detected_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)`
    )
      .bind(
        messageId, senderId, recipientId, signal.score,
        signal.hasPaymentDemand ? 1 : 0,
        signal.hasImageThreat ? 1 : 0,
        signal.hasCounting ? 1 : 0,
        signal.hasPersonalData ? 1 : 0
      )
      .run();

    if (signal.score >= 0.75) {
      await env.THREAT_QUEUE.send({
        type: "SEXTORTION_HIGH",
        messageId,
        senderId,
        recipientId,
        score: signal.score,
        ts: Date.now(),
      });
      // Block delivery; preserve evidence in KV with extended TTL
      await env.MESSAGE_KV.put(
        `evidence:${messageId}`,
        JSON.stringify({ body, signal }),
        { expirationTtl: 60 * 60 * 24 * 90 }  // 90 days for legal hold
      );
      return new Response(JSON.stringify({ action: "block", reason: "sextortion" }), { status: 200 });
    }

    if (signal.score >= 0.45) {
      await env.THREAT_QUEUE.send({
        type: "SEXTORTION_REVIEW",
        messageId,
        senderId,
        score: signal.score,
        ts: Date.now(),
      });
      // Deliver but flag; show recipient safety resources
      return new Response(JSON.stringify({ action: "allow", flag: "sextortion_review" }), { status: 200 });
    }

    return new Response(JSON.stringify({ action: "allow" }), { status: 200 });
  },
};
```

## Response and Enforcement — Escalation Queue Consumer

```typescript
// workers/sextortion-responder.ts
interface ThreatEvent {
  type: "SEXTORTION_HIGH" | "SEXTORTION_REVIEW";
  messageId: string;
  senderId: string;
  recipientId?: string;
  score: number;
  ts: number;
}

export default {
  async queue(batch: MessageBatch<ThreatEvent>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const evt = msg.body;

      if (evt.type === "SEXTORTION_HIGH") {
        // 1. Suspend sender session immediately
        await env.DB.prepare(
          `UPDATE anonymous_sessions SET status = 'suspended',
             suspension_reason = 'sextortion', suspended_at = CURRENT_TIMESTAMP
           WHERE session_id = ?`
        ).bind(evt.senderId).run();

        // 2. Record victim notification intent (never store recipient PII)
        await env.DB.prepare(
          `INSERT INTO victim_notifications
             (message_id, recipient_session_id, resource_url, notified_at)
           VALUES (?, ?, 'https://example.com/safety/sextortion-help', CURRENT_TIMESTAMP)`
        ).bind(evt.messageId, evt.recipientId ?? "unknown").run();

        // 3. Increment sender threat counter for NCMEC-report threshold
        await env.DB.prepare(
          `INSERT INTO sender_threat_counts (sender_id, threat_type, count, window_start)
             VALUES (?, 'sextortion', 1, CURRENT_TIMESTAMP)
           ON CONFLICT(sender_id, threat_type) DO UPDATE
             SET count = count + 1`
        ).bind(evt.senderId).run();

        const { results } = await env.DB.prepare(
          `SELECT count FROM sender_threat_counts WHERE sender_id = ? AND threat_type = 'sextortion'`
        ).bind(evt.senderId).all<{ count: number }>();

        if ((results[0]?.count ?? 0) >= 3) {
          await env.DB.prepare(
            `INSERT INTO ncmec_report_queue (sender_id, trigger_message_id, queued_at)
               VALUES (?, ?, CURRENT_TIMESTAMP)`
          ).bind(evt.senderId, evt.messageId).run();
        }
      }

      msg.ack();
    }
  },
};
```

## Audit and Compliance — Legal Hold and Reporting

```typescript
// workers/sextortion-audit.ts
// D1 schema additions (run via migration):
const SCHEMA = `
CREATE TABLE IF NOT EXISTS sextortion_signals (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id       TEXT    NOT NULL UNIQUE,
  sender_id        TEXT    NOT NULL,
  recipient_id     TEXT,
  score            REAL    NOT NULL,
  has_payment_demand INTEGER DEFAULT 0,
  has_image_threat   INTEGER DEFAULT 0,
  has_counting       INTEGER DEFAULT 0,
  has_personal_data  INTEGER DEFAULT 0,
  detected_at      TEXT    NOT NULL,
  legal_hold       INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS victim_notifications (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id           TEXT NOT NULL,
  recipient_session_id TEXT NOT NULL,
  resource_url         TEXT NOT NULL,
  notified_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ncmec_report_queue (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  sender_id        TEXT NOT NULL,
  trigger_message_id TEXT NOT NULL,
  queued_at        TEXT NOT NULL,
  reported_at      TEXT,
  ncmec_report_id  TEXT
);

CREATE INDEX IF NOT EXISTS idx_sextortion_sender ON sextortion_signals(sender_id);
CREATE INDEX IF NOT EXISTS idx_sextortion_score  ON sextortion_signals(score);
`;

export async function auditReport(env: Env): Promise<Record<string, unknown>> {
  const [highRisk, holds, reportsPending] = await Promise.all([
    env.DB.prepare(
      `SELECT COUNT(*) as c FROM sextortion_signals WHERE score >= 0.75 AND detected_at > datetime('now','-7 days')`
    ).first<{ c: number }>(),
    env.DB.prepare(
      `SELECT COUNT(*) as c FROM sextortion_signals WHERE legal_hold = 1`
    ).first<{ c: number }>(),
    env.DB.prepare(
      `SELECT COUNT(*) as c FROM ncmec_report_queue WHERE reported_at IS NULL`
    ).first<{ c: number }>(),
  ]);

  return {
    period: "7d",
    highRiskMessages: highRisk?.c ?? 0,
    evidenceOnLegalHold: holds?.c ?? 0,
    ncmecReportsPending: reportsPending?.c ?? 0,
    generatedAt: new Date().toISOString(),
  };
}
```

## Anti-patterns

- **Notifying the sender that detection fired** — tips off offenders to rephrase; always block silently.
- **Storing message bodies in D1** — bodies belong in KV/R2 with restricted access; D1 holds only signals and metadata.
- **Binary block on scores below 0.75** — generates false-positive blocks on consensual adult content; use the review tier.
- **Sharing victim session IDs in NCMEC reports** — reports should reference the offending sender, not the victim.
- **Reusing evidence KV keys across incidents** — collision overwrites prior evidence; always key by `evidence:{messageId}`.

## Gotchas

- Workers AI `llama-3.1-8b-instruct` token budget: keep prompt + body under 1 024 tokens or truncate body safely.
- D1 `ON CONFLICT` upsert requires the conflicting column to have a `UNIQUE` or `PRIMARY KEY` constraint — add it in migrations.
- KV `expirationTtl` is in **seconds**, not milliseconds; 90 days = `60 * 60 * 24 * 90`.
- Queue consumers must call `msg.ack()` even on no-op paths; unacknowledged messages retry and cause double-escalation.
- NCMEC CyberTipline submissions require a registered ESP account and must include a hash of the offending image if available — text-only cases still require a written narrative report.

## Verification

```bash
# 1. Unit test classifier against known sextortion template
curl -X POST https://example.com/internal/sextortion-detect \
  -H "Content-Type: application/json" \
  -d '{"senderId":"s1","recipientId":"r1","messageId":"m1",
       "body":"Send $500 in BTC or I leak your nudes to everyone you know. 24 hours."}'
# Expect: {"action":"block","reason":"sextortion"}

# 2. Confirm D1 row written
wrangler d1 execute example project-db --command \
  "SELECT score, has_image_threat FROM sextortion_signals WHERE message_id = 'm1';"

# 3. Confirm KV evidence key set
wrangler kv:key get --namespace-id=<NS_ID> "evidence:m1"

# 4. Confirm sender session suspended
wrangler d1 execute example project-db --command \
  "SELECT status FROM anonymous_sessions WHERE session_id = 's1';"

# 5. Validate non-threatening message is allowed without AI call (fast-path)
curl -X POST https://example.com/internal/sextortion-detect \
  -H "Content-Type: application/json" \
  -d '{"senderId":"s2","recipientId":"r2","messageId":"m2","body":"Hey, how are you?"}'
# Expect: {"action":"allow"}
```

## Related

- `grooming-pattern-detection-dms-workers-ai.md`
- `legal-hold-evidence-preservation-d1-r2.md`
- `real-time-toxic-content-scoring-workers-ai.md`
- `anonymous-content-reporting-worker-pipeline.md`

## Sources

- https://www.ncmec.org/cybertipline/
- https://www.iwf.org.uk/what-we-do/how-we-assess-and-remove-content/sextortion/
- https://www.stopncii.org/
