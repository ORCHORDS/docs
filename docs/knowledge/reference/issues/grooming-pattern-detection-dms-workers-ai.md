# Grooming Pattern Detection in DMs via Workers AI

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
An anonymous platform receives reports of adults grooming minors through direct messages. Real-time pattern detection is needed to flag and queue suspicious conversations before human review.

## Context
Grooming often follows recognizable linguistic progressions: requests for age/location, gift offers, isolation tactics, and escalating personal disclosure. Workers AI can score message sequences in-flight using a fine-tuned or prompted text-classification model. Flagged conversations are queued for Trust & Safety review and the session is rate-limited immediately while investigation is pending.

## Message Ingestion and Age-Context Tagging

Attach an `underageFlag` to each conversation thread stored in D1. Any thread where either participant was tagged during age-verification (see `underage-user-detection-behavioral-signals.md`) is treated as elevated risk.

```typescript
// worker: dm-ingest.ts
export interface Env {
  DB: D1Database;
  REVIEW_QUEUE: Queue;
  AI: Ai;
}

interface DMPayload {
  threadId: string;
  senderId: string;
  recipientId: string;
  body: string;
  sentAt: string;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const dm = await req.json<DMPayload>();

    await env.DB.prepare(
      `INSERT INTO messages (thread_id, sender_id, recipient_id, body, sent_at)
       VALUES (?, ?, ?, ?, ?)`
    ).bind(dm.threadId, dm.senderId, dm.recipientId, dm.body, dm.sentAt).run();

    const { results } = await env.DB.prepare(
      `SELECT underage_flag FROM thread_meta WHERE thread_id = ?`
    ).bind(dm.threadId).all<{ underage_flag: number }>();

    const elevatedRisk = results[0]?.underage_flag === 1;
    await scoreMessage(dm, elevatedRisk, env);

    return new Response("ok");
  },
};
```

## Grooming Signal Scoring with Workers AI

Build a rolling context window of the last N messages and submit them as a structured prompt to Workers AI. The model returns a grooming-risk score (0–1) and the dominant signal category.

```typescript
async function scoreMessage(dm: DMPayload, elevated: boolean, env: Env) {
  const { results: recent } = await env.DB.prepare(
    `SELECT sender_id, body FROM messages
     WHERE thread_id = ? ORDER BY sent_at DESC LIMIT 20`
  ).bind(dm.threadId).all<{ sender_id: string; body: string }>();

  const transcript = recent
    .reverse()
    .map((m) => `[${m.sender_id}]: ${m.body}`)
    .join("\n");

  const response = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [
      {
        role: "system",
        content:
          "You are a trust-and-safety classifier. Analyze the conversation for grooming signals: " +
          "age/location solicitation, isolation tactics, unsolicited gifts, secret-keeping requests, " +
          "escalating personal disclosure. Return JSON {score: 0-1, signal: string}.",
      },
      { role: "user", content: transcript },
    ],
  }) as { response: string };

  let parsed: { score: number; signal: string } = { score: 0, signal: "none" };
  try {
    parsed = JSON.parse(response.response);
  } catch {
    /* malformed model output — default to safe */
  }

  const threshold = elevated ? 0.45 : 0.7;
  if (parsed.score >= threshold) {
    await env.REVIEW_QUEUE.send({
      threadId: dm.threadId,
      score: parsed.score,
      signal: parsed.signal,
      elevated,
      flaggedAt: new Date().toISOString(),
    });
  }
}
```

## Review Queue Consumer and Session Rate-Limiting

A separate Queue consumer worker reads flagged threads, writes a review ticket to D1, and immediately rate-limits the sender's session via KV so they cannot continue messaging at volume while under review.

```typescript
// worker: dm-review-consumer.ts
export interface Env {
  DB: D1Database;
  SESSION_KV: KVNamespace;
}

export default {
  async queue(batch: MessageBatch, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { threadId, score, signal, elevated, flaggedAt } =
        msg.body as {
          threadId: string;
          score: number;
          signal: string;
          elevated: boolean;
          flaggedAt: string;
        };

      await env.DB.prepare(
        `INSERT OR IGNORE INTO review_tickets
         (thread_id, score, signal, elevated, flagged_at, status)
         VALUES (?, ?, ?, ?, ?, 'pending')`
      ).bind(threadId, score, signal, elevated ? 1 : 0, flaggedAt).run();

      // Fetch sender to rate-limit their outbound DMs
      const { results } = await env.DB.prepare(
        `SELECT DISTINCT sender_id FROM messages
         WHERE thread_id = ? ORDER BY sent_at DESC LIMIT 1`
      ).bind(threadId).all<{ sender_id: string }>();

      if (results[0]) {
        await env.SESSION_KV.put(
          `dm_ratelimit:${results[0].sender_id}`,
          "1",
          { expirationTtl: 86400 } // 24 h hold pending review
        );
      }

      msg.ack();
    }
  },
};
```

## Reviewer Dashboard Endpoint

Trust & Safety reviewers query pending tickets with thread context to make accept/escalate/clear decisions.

```typescript
// GET /review/:threadId
export async function getReviewContext(
  threadId: string,
  env: Env
): Promise<Response> {
  const [ticket, messages] = await Promise.all([
    env.DB.prepare(
      `SELECT * FROM review_tickets WHERE thread_id = ?`
    ).bind(threadId).first(),
    env.DB.prepare(
      `SELECT sender_id, body, sent_at FROM messages
       WHERE thread_id = ? ORDER BY sent_at ASC`
    ).bind(threadId).all(),
  ]);

  return Response.json({ ticket, messages: messages.results });
}
```

## Anti-patterns
- Scoring every individual message in isolation — grooming context spans multiple turns and single-message scoring produces too many false positives
- Blocking accounts immediately without human review — use rate-limiting and queue, not hard bans, until a human confirms
- Storing full message bodies in review tickets without encryption — use envelope encryption via Workers KV + WASM crypto
- Relying on keyword lists alone — adversarial senders obfuscate keywords; semantic scoring is required

## Gotchas
- Workers AI response may not always return valid JSON — always try/catch the parse and default to a safe score of 0
- D1 `INSERT OR IGNORE` prevents duplicate tickets if the queue consumer retries a batch
- The 6 MB message size limit on Queues means very long transcripts should be stored in D1 and the queue message should carry only the `threadId`
- `expirationTtl` on KV rate-limit keys must outlast the expected review SLA; use a longer TTL for elevated-risk threads

## Verification
1. Seed a D1 test database with a known grooming transcript and confirm a review ticket is created with `score >= threshold`.
2. Assert the sender's `dm_ratelimit:` KV key exists after the queue consumer processes the flag.
3. Call the reviewer endpoint and verify the full message history is returned alongside the ticket metadata.
4. Test with a benign conversation and verify no ticket is created and no KV key is set.

## Related
- [`underage-user-detection-behavioral-signals.md`](underage-user-detection-behavioral-signals.md)
- [`crisis-intervention-detection-workers-ai.md`](crisis-intervention-detection-workers-ai.md)
- [`repeat-offender-detection-anonymous-sessions.md`](repeat-offender-detection-anonymous-sessions.md)
- [`real-time-toxic-content-scoring-workers-ai.md`](real-time-toxic-content-scoring-workers-ai.md)

## Sources
- NCMEC CyberTipline reporting requirements (2025)
- Thorn "Survivor Insights" grooming pattern taxonomy (2024)
- Cloudflare Workers AI documentation — `@cf/meta/llama-3.1-8b-instruct`
- EU DSA Article 36 — risk mitigation for illegal content involving minors
