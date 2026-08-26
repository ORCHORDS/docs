# Harassment Pattern Detection with Durable Objects

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

On example project, individual messages are often benign in isolation but constitute coordinated harassment when viewed as a sequence targeting a specific recipient session. Stateless Workers cannot accumulate per-target interaction history across requests, so existing moderation only inspects single messages and misses orchestrated pile-on patterns that emerge over minutes or hours.

## Context

Harassment on anonymous platforms frequently takes the form of sustained targeting: many senders directing a stream of negative interactions at one recipient, or a single sender cycling through anonymous sessions to maintain pressure. Cloudflare Durable Objects are the correct primitive for this problem because they provide strongly consistent, co-located state that accumulates interaction history keyed to a target session identifier without requiring an external database round-trip on every message. The Durable Object maintains a rolling window of interaction metadata — sender fingerprint, sentiment score, message count, and timestamps — and applies pattern rules to emit a harassment score that the ingestion Worker uses to suppress or flag content before it reaches the target.

## Durable Object: Per-Target Interaction Accumulator

Each recipient session owns one Durable Object instance. The object holds the last 60 minutes of interaction events in its in-memory state and persists a summary to Durable Object storage every 5 minutes to survive eviction. Sentiment scores come from a Workers AI text classification call made in the ingestion Worker before the DO is contacted, keeping the DO logic pure and fast.

```typescript
export interface Env {
  HARASSMENT_DO: DurableObjectNamespace;
  AI: Ai;
  DB: D1Database;
}

interface InteractionEvent {
  senderId: string;      // hashed fingerprint — not a persistent account ID
  sentimentScore: number; // -1.0 (very negative) to 1.0 (very positive)
  ts: number;            // unix ms
}

interface HarassmentState {
  events: InteractionEvent[];
  lastPersisted: number;
}

const WINDOW_MS = 60 * 60 * 1000; // 1 hour rolling window
const PERSIST_INTERVAL_MS = 5 * 60 * 1000;

export class TargetHarassmentAccumulator implements DurableObject {
  private state: HarassmentState = { events: [], lastPersisted: 0 };
  private initialized = false;

  constructor(private ctx: DurableObjectState, private env: Env) {}

  private async ensureLoaded(): Promise<void> {
    if (this.initialized) return;
    const stored = await this.ctx.storage.get<HarassmentState>('state');
    if (stored) this.state = stored;
    this.initialized = true;
  }

  private pruneWindow(now: number): void {
    this.state.events = this.state.events.filter(
      (e) => now - e.ts < WINDOW_MS,
    );
  }

  private async maybePersist(now: number): Promise<void> {
    if (now - this.state.lastPersisted > PERSIST_INTERVAL_MS) {
      this.state.lastPersisted = now;
      await this.ctx.storage.put('state', this.state);
    }
  }

  async fetch(request: Request): Promise<Response> {
    await this.ensureLoaded();

    if (request.method === 'POST') {
      const event = await request.json<InteractionEvent>();
      const now = Date.now();

      this.pruneWindow(now);
      this.state.events.push({ ...event, ts: now });
      await this.maybePersist(now);

      const score = this.computeHarassmentScore();
      return Response.json(score);
    }

    if (request.method === 'GET') {
      await this.ensureLoaded();
      return Response.json(this.computeHarassmentScore());
    }

    return new Response('Method not allowed', { status: 405 });
  }

  private computeHarassmentScore(): {
    score: number;
    verdict: 'CLEAN' | 'WARNING' | 'HARASSMENT';
    uniqueSenders: number;
    negativeCount: number;
    totalCount: number;
  } {
    const now = Date.now();
    const recentEvents = this.state.events.filter(
      (e) => now - e.ts < 15 * 60 * 1000, // last 15 min for scoring
    );

    const uniqueSenders = new Set(recentEvents.map((e) => e.senderId)).size;
    const negativeCount = recentEvents.filter((e) => e.sentimentScore < -0.3).length;
    const totalCount = recentEvents.length;

    // Harassment score: high if many senders send negative content rapidly
    const velocityFactor = Math.min(totalCount / 10, 1); // saturates at 10 messages
    const negativeFraction = totalCount > 0 ? negativeCount / totalCount : 0;
    const pileonFactor = Math.min(uniqueSenders / 5, 1); // saturates at 5 unique senders

    const score = (velocityFactor * 0.4 + negativeFraction * 0.4 + pileonFactor * 0.2);

    const verdict: 'CLEAN' | 'WARNING' | 'HARASSMENT' =
      score >= 0.75 ? 'HARASSMENT' : score >= 0.45 ? 'WARNING' : 'CLEAN';

    return { score, verdict, uniqueSenders, negativeCount, totalCount };
  }
}
```

## Ingestion Worker: Sentiment Scoring and DO Dispatch

The ingestion Worker runs sentiment analysis on the message text, hashes the sender fingerprint, then contacts the target's Durable Object. If the DO returns `HARASSMENT`, the message is blocked and logged to D1; if `WARNING`, it passes but adds the target to a human review queue.

```typescript
async function scoreSentiment(ai: Ai, text: string): Promise<number> {
  const result = await ai.run('@cf/huggingface/distilbert-sst-2-int8', {
    text,
  }) as Array<{ label: string; score: number }>;

  const positive = result.find((r) => r.label === 'POSITIVE');
  const negative = result.find((r) => r.label === 'NEGATIVE');

  if (!positive || !negative) return 0;
  return positive.score - negative.score; // range [-1, 1]
}

async function hashFingerprint(raw: string): Promise<string> {
  const buf = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(raw),
  );
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { text, targetSessionId, senderFingerprint, messageId } =
      await request.json<{
        text: string;
        targetSessionId: string;
        senderFingerprint: string;
        messageId: string;
      }>();

    // Sentiment score (Workers AI)
    const sentimentScore = await scoreSentiment(env.AI, text);

    // Hash sender fingerprint before storing anywhere
    const senderIdHash = await hashFingerprint(senderFingerprint);

    // Contact the target's Durable Object
    const doId = env.HARASSMENT_DO.idFromName(targetSessionId);
    const stub = env.HARASSMENT_DO.get(doId);

    const doResponse = await stub.fetch('https://do/events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        senderId: senderIdHash,
        sentimentScore,
        ts: Date.now(),
      } satisfies InteractionEvent),
    });

    const score = await doResponse.json<{
      score: number;
      verdict: 'CLEAN' | 'WARNING' | 'HARASSMENT';
      uniqueSenders: number;
      negativeCount: number;
    }>();

    if (score.verdict === 'HARASSMENT') {
      await env.DB.prepare(
        `INSERT INTO harassment_blocks
           (message_id, target_session, sender_hash, harassment_score, unique_senders, created_at)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6)`,
      )
        .bind(messageId, targetSessionId, senderIdHash, score.score, score.uniqueSenders, new Date().toISOString())
        .run();

      return Response.json({ blocked: true, verdict: 'HARASSMENT' }, { status: 403 });
    }

    return Response.json({ blocked: false, verdict: score.verdict });
  },
} satisfies ExportedHandler<Env>;
```

## D1 Schema

```sql
-- migration: 0008_harassment_detection.sql
CREATE TABLE IF NOT EXISTS harassment_blocks (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id        TEXT NOT NULL UNIQUE,
  target_session    TEXT NOT NULL,
  sender_hash       TEXT NOT NULL,
  harassment_score  REAL NOT NULL,
  unique_senders    INTEGER NOT NULL,
  created_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_harassment_target
  ON harassment_blocks(target_session, created_at DESC);
```

## Anti-patterns

- Keying the Durable Object on the sender rather than the target — the pattern to detect is the pile-on against one recipient, not the behavior of one sender across many targets (the latter is covered by repeat-offender detection).
- Persisting every event synchronously to Durable Object storage on every message; this turns each `fetch` into a storage write and introduces unnecessary latency — batch persist on interval instead.
- Using wall-clock time in the DO without accounting for eviction: after the DO is evicted and reloaded, `Date.now()` differs from stored `ts` values — always prune relative to `Date.now()` at load time, not at write time.

## Gotchas

- Durable Objects have a single-threaded concurrency model; concurrent `POST` requests to the same DO instance are queued. Under very high-volume targeting (> 50 messages/second to one target), request queuing adds latency — shed load with a probabilistic drop before reaching the DO.
- `idFromName` returns the same DO for the same string on every invocation; if you rotate target session IDs (e.g., on logout), the old DO retains stale state until its alarm or eviction — register an alarm to delete storage on session expiry.

## Verification

```bash
# Simulate a pile-on: 6 unique fingerprints sending negative messages
for i in {1..6}; do
  curl -s -X POST https://example project-ingest.example.workers.dev/message \
    -H "Content-Type: application/json" \
    -d "{\"text\":\"you are terrible\",\"targetSessionId\":\"sess_target\",\"senderFingerprint\":\"fp_$i\",\"messageId\":\"msg_$i\"}"
done

# Check blocks in D1
wrangler d1 execute example project-db \
  --command "SELECT target_session, harassment_score, unique_senders, created_at FROM harassment_blocks ORDER BY created_at DESC LIMIT 10"
```

## Related

- `issues/repeat-offender-detection-anonymous-sessions.md`
- `issues/platform-manipulation-brigading-detection.md`
- `issues/shadow-banning-reach-limiting-d1-workers.md`
- `issues/viral-content-cascade-rate-limiting-durable-objects.md`

## Sources

- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/workers-ai/models/distilbert-sst-2-int8/
- https://developers.cloudflare.com/durable-objects/api/alarms/
