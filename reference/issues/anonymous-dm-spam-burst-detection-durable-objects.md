# Anonymous DM Spam Burst Detection with Durable Objects Rate Limiting

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project (example.com) allows anonymous direct messages between users who have mutually opted in. Spam actors exploit this by sending hundreds of identical or near-identical DMs in rapid bursts to farm engagement, phish recipients with external links, or harass targets. Because accounts are anonymous, traditional sender-reputation systems tied to email history or verified identity are unavailable.

The symptom manifests as a sudden spike in DM volume from a single anonymous session token — dozens of DMs in a few seconds, often to accounts the sender has never interacted with before. Without detection, the recipient side sees a flooded inbox and the platform's trust score drops when users report the experience.

## Context

Cloudflare Durable Objects are the correct primitive for this problem on example project Each anonymous sender gets their own Durable Object instance acting as a stateful rate-limiter and burst detector. The object holds an in-memory sliding-window counter and a D1-backed persistent record of prior violations. Because Durable Objects run in a single-threaded, geographically-colocated context, there is no race condition on counter updates — a property that is impossible to guarantee with a shared KV or D1 counter under concurrent requests.

Workers AI is used to score the semantic similarity of the burst messages in real time. If twenty messages in sixty seconds all have a cosine similarity above 0.95, the burst is flagged as templated spam even if minor word substitutions were applied to defeat simple exact-match deduplication.

## Durable Object: Per-Sender Rate Limiter

Each anonymous sender token maps to one Durable Object. The object tracks a sliding window of message timestamps and checks Workers AI similarity when a burst threshold is crossed.

```typescript
// durable-object: SenderLimiter.ts
export interface Env {
  DB: D1Database;
  AI: Ai;
}

interface WindowEntry {
  ts: number;
  contentHash: string;
  embedding?: number[];
}

const WINDOW_MS = 60_000;        // 1-minute sliding window
const BURST_THRESHOLD = 15;       // messages before scrutiny starts
const HARD_LIMIT = 40;            // messages → automatic block
const SIMILARITY_THRESHOLD = 0.95;

export class SenderLimiter implements DurableObject {
  private window: WindowEntry[] = [];
  private blocked = false;
  private blockUntil = 0;

  constructor(
    private readonly state: DurableObjectState,
    private readonly env: Env
  ) {
    this.state.blockConcurrencyWhile(async () => {
      this.blocked = (await this.state.storage.get<boolean>('blocked')) ?? false;
      this.blockUntil = (await this.state.storage.get<number>('blockUntil')) ?? 0;
    });
  }

  async fetch(request: Request): Promise<Response> {
    const now = Date.now();

    // Lift block if expiry has passed
    if (this.blocked && now >= this.blockUntil) {
      this.blocked = false;
      await this.state.storage.put('blocked', false);
    }

    if (this.blocked) {
      return new Response(JSON.stringify({ allowed: false, reason: 'burst_blocked' }), {
        status: 429,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const body = await request.json<{ senderId: string; content: string }>();

    // Prune entries outside the sliding window
    this.window = this.window.filter(e => now - e.ts < WINDOW_MS);

    const contentHash = await this.hashContent(body.content);

    if (this.window.length >= HARD_LIMIT) {
      await this.applyBlock(body.senderId, now, 'hard_limit');
      return new Response(JSON.stringify({ allowed: false, reason: 'hard_limit' }), {
        status: 429,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    if (this.window.length >= BURST_THRESHOLD) {
      const spamDetected = await this.detectSpamBurst(body.content, contentHash, now);
      if (spamDetected) {
        await this.applyBlock(body.senderId, now, 'spam_burst');
        return new Response(JSON.stringify({ allowed: false, reason: 'spam_burst' }), {
          status: 429,
          headers: { 'Content-Type': 'application/json' },
        });
      }
    }

    this.window.push({ ts: now, contentHash });
    return new Response(JSON.stringify({ allowed: true }), {
      headers: { 'Content-Type': 'application/json' },
    });
  }

  private async detectSpamBurst(
    newContent: string,
    newHash: string,
    _now: number
  ): Promise<boolean> {
    // Fast path: exact hash duplicates
    const dupeCount = this.window.filter(e => e.contentHash === newHash).length;
    if (dupeCount >= 5) return true;

    // Slow path: semantic similarity via Workers AI embeddings
    try {
      const textsToEmbed = [
        newContent,
        ...this.window.slice(-10).map(e => e.contentHash), // we stored hashes; in prod store short content snippets
      ];

      const response = await this.env.AI.run('@cf/baai/bge-small-en-v1.5', {
        text: [newContent],
      }) as { data: number[][] };

      const newEmbedding = response.data[0];

      let highSimCount = 0;
      for (const entry of this.window.slice(-10)) {
        if (entry.embedding) {
          const sim = cosineSimilarity(newEmbedding, entry.embedding);
          if (sim >= SIMILARITY_THRESHOLD) highSimCount++;
        }
      }

      // Attach embedding for future comparisons
      this.window[this.window.length - 1] = {
        ...this.window[this.window.length - 1],
        embedding: newEmbedding,
      };

      return highSimCount >= 5;
    } catch {
      // AI unavailable — fall back to hash-only check
      return dupeCount >= 8;
    }
  }

  private async applyBlock(
    senderId: string,
    now: number,
    reason: string
  ): Promise<void> {
    const blockDuration = 30 * 60 * 1000; // 30 minutes
    this.blocked = true;
    this.blockUntil = now + blockDuration;
    await this.state.storage.put('blocked', true);
    await this.state.storage.put('blockUntil', this.blockUntil);

    // Persist violation to D1 for audit and repeat-offender tracking
    await this.env.DB.prepare(`
      INSERT INTO dm_violations (sender_id, reason, occurred_at, block_until)
      VALUES (?1, ?2, unixepoch(), ?3)
    `).bind(senderId, reason, Math.floor(this.blockUntil / 1000)).run();
  }

  private async hashContent(content: string): Promise<string> {
    const encoder = new TextEncoder();
    const data = encoder.encode(content.toLowerCase().replace(/\s+/g, ' ').trim());
    const hashBuffer = await crypto.subtle.digest('SHA-256', data);
    return Array.from(new Uint8Array(hashBuffer))
      .map(b => b.toString(16).padStart(2, '0'))
      .join('')
      .slice(0, 16); // short prefix sufficient for in-memory dedup
  }
}

function cosineSimilarity(a: number[], b: number[]): number {
  if (a.length !== b.length) return 0;
  let dot = 0, normA = 0, normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  return dot / (Math.sqrt(normA) * Math.sqrt(normB) || 1);
}
```

## Worker: DM Gateway

The DM submission Worker routes each message through the sender's Durable Object before persisting it, providing a synchronous gate with sub-millisecond Durable Object latency when the object is already warm.

```typescript
// worker: dm-gateway.ts
export interface Env {
  SENDER_LIMITER: DurableObjectNamespace;
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const body = await request.json<{
      senderId: string;
      recipientId: string;
      content: string;
    }>();

    if (!body.senderId || !body.recipientId || !body.content) {
      return new Response('Bad Request', { status: 400 });
    }

    if (body.content.length > 2000) {
      return new Response('Message too long', { status: 413 });
    }

    // Route to sender's Durable Object for rate-limit check
    const id = env.SENDER_LIMITER.idFromName(body.senderId);
    const stub = env.SENDER_LIMITER.get(id);

    const checkResponse = await stub.fetch('https://internal/check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ senderId: body.senderId, content: body.content }),
    });

    const { allowed, reason } = await checkResponse.json<{
      allowed: boolean;
      reason?: string;
    }>();

    if (!allowed) {
      return new Response(
        JSON.stringify({ error: 'Rate limited', reason }),
        { status: 429, headers: { 'Content-Type': 'application/json' } }
      );
    }

    // Persist approved DM
    await env.DB.prepare(`
      INSERT INTO direct_messages (sender_id, recipient_id, content, sent_at)
      VALUES (?1, ?2, ?3, unixepoch())
    `).bind(body.senderId, body.recipientId, body.content).run();

    return new Response(JSON.stringify({ ok: true }), {
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

## Violation History and Repeat Offender Escalation

A separate Worker reads `dm_violations` in D1 and escalates accounts that accumulate multiple violations within a rolling 24-hour window to a higher-severity queue for manual review or automatic shadow-ban.

```typescript
// worker: violation-escalator.ts (scheduled every 10 minutes)
export interface Env {
  DB: D1Database;
  REPORT_QUEUE: Queue;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // Find senders with 3+ violations in the past 24 hours not yet escalated
    const offenders = await env.DB.prepare(`
      SELECT sender_id, COUNT(*) AS violation_count
      FROM dm_violations
      WHERE occurred_at > unixepoch() - 86400
        AND escalated = 0
      GROUP BY sender_id
      HAVING violation_count >= 3
    `).all<{ sender_id: string; violation_count: number }>();

    for (const offender of offenders.results) {
      await env.REPORT_QUEUE.send({
        type: 'repeat_dm_spammer',
        senderId: offender.sender_id,
        violationCount: offender.violation_count,
        priority: 'high',
        detectedAt: new Date().toISOString(),
      });

      await env.DB.prepare(`
        UPDATE dm_violations SET escalated = 1
        WHERE sender_id = ?1 AND occurred_at > unixepoch() - 86400
      `).bind(offender.sender_id).run();
    }
  },
};
```

## Anti-patterns

- Using Cloudflare KV as the rate-limit counter store — KV has eventual consistency; two concurrent DM requests can both read a stale count and both pass the threshold simultaneously; Durable Objects are the only correct choice for per-sender counters under concurrent load
- Storing full message content in the Durable Object `window` array — Durable Object memory is limited to 128 MB; store only a short hash or a truncated snippet (first 100 chars) for similarity comparison seeding
- Running Workers AI embedding on every message — invoke AI only when the burst threshold is already crossed; below that threshold, hash-based dedup is sufficient and orders of magnitude cheaper
- Setting the block duration to hours on first offense — a 30-minute block is enough for a burst actor; long blocks create false-positive friction for legitimate users who hit a bug in their client that caused a retry loop
- Forgetting to handle the case where `blockConcurrencyWhile` storage retrieval throws — wrap in try/catch and fail open (allow the message) to avoid Durable Object startup crashes blocking all DMs

## Gotchas

- Durable Object `fetch()` handlers must return a `Response`; throwing an unhandled error causes the calling Worker to receive a 500 and the Durable Object to log an uncaught exception — always wrap the handler body in try/catch
- The `@cf/baai/bge-small-en-v1.5` embedding model is suitable for short texts; for messages over 512 tokens the embedding quality degrades — truncate content before embedding
- Workers AI `run()` counts against the account's AI Gateway quota even in development; use a mock in local `wrangler dev` runs
- `DurableObjectNamespace.idFromName()` is deterministic; two Workers calling `idFromName(sameSenderId)` will get the same object, but only within the same Cloudflare account and binding name
- D1's `unixepoch()` returns an integer; storing `block_until` as an integer seconds value and comparing it to `Date.now() / 1000` is correct — do not mix milliseconds and seconds across the boundary

## Verification

1. Deploy the Durable Object and Worker to a test environment with `wrangler deploy --env staging`.
2. Write a load test that sends 20 identical DMs within 5 seconds from the same `senderId`.
3. Assert that the first 14 succeed (HTTP 200) and messages 15-40 return 429 with `reason: spam_burst`.
4. Inspect `dm_violations` in D1 — expect one row for the sender with `reason = 'hard_limit'` or `'spam_burst'`.
5. Wait 31 minutes (or manually reset storage in the DO) and confirm the block lifts.
6. Send 3 bursts separated by 11 minutes each (enough to reset the sliding window but still trigger the repeat-offender check) and confirm a `repeat_dm_spammer` message appears in the REPORT_QUEUE consumer.

## Related

- `harassment-pattern-detection-durable-objects.md`
- `viral-content-cascade-rate-limiting-durable-objects.md`
- `spam-post-detection-cloudflare-workers-ai.md`
- `report-queue-prioritization-workers-queues-ai.md`

## Sources

- Cloudflare Durable Objects documentation: https://developers.cloudflare.com/durable-objects/
- Workers AI text embedding models: https://developers.cloudflare.com/workers-ai/models/
- Cloudflare Queues documentation: https://developers.cloudflare.com/queues/
