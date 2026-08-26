# Email Engagement Scoring and Behavioral Segmentation

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A growing subscriber list suffers declining open rates, rising spam complaints, and
inbox providers downgrading sender reputation. Bulk broadcasts to 200 000 subscribers
treat a daily opener and a six-month ghost identically. Deliverability degrades because
ISPs interpret low engagement as a spam signal. Engagement scoring segments subscribers
by their recent behavior — opens, clicks, purchases triggered by email — and allows the
sender to suppress inactive contacts, warm up lapsed ones, and concentrate high-volume
sends on the most engaged cohort where inbox placement is strongest.

## Context

Engagement scoring assigns a numeric value to each subscriber that decays over time and
increases on activity. The score drives list segmentation (Champions, Active, At-Risk,
Lapsed, Dormant) which in turn controls send frequency, cadence, and content tier.
Cloudflare D1 provides a persistent subscriber score store accessible from Workers at
low latency. Cloudflare Queues absorb webhook events from the ESP and process them
asynchronously to avoid blocking the delivery pipeline.

## Scoring Model

A time-decayed point model based on recency and frequency is the most portable approach:

| Event              | Base Points | Notes                              |
|--------------------|-------------|------------------------------------|
| Email open         | +2          | Unreliable post Apple MPP (2021)   |
| Unique click       | +5          | Most reliable engagement signal    |
| Purchase from email| +20         | Requires conversion attribution    |
| Unsubscribe click  | -50         | Hard remove; score irrelevant      |
| Spam complaint     | -100        | Suppress immediately               |
| Bounce (hard)      | -100        | Suppress immediately               |
| Bounce (soft ×3)   | -50         | Three consecutive soft bounces     |

**Decay formula** — recalculate score on each read, not on each write:

```
effectiveScore = baseScore × e^(-λ × daysSinceLastActivity)
```

Where `λ = ln(2) / halfLifeDays`. A 90-day half-life means a score of 100 today reads
as 50 after 90 days of silence, and 25 after 180 days — without touching the stored row.

## D1 Schema

```sql
CREATE TABLE subscriber_scores (
  subscriber_id   TEXT    PRIMARY KEY,  -- UUID or email hash
  email           TEXT    NOT NULL UNIQUE,
  base_score      REAL    NOT NULL DEFAULT 0,
  last_event_at   INTEGER NOT NULL,     -- Unix ms of most recent scored event
  last_event_type TEXT,
  segment         TEXT    NOT NULL DEFAULT 'new',
  created_at      INTEGER NOT NULL,
  updated_at      INTEGER NOT NULL
);

CREATE INDEX idx_subscriber_scores_segment ON subscriber_scores(segment);
CREATE INDEX idx_subscriber_scores_last_event ON subscriber_scores(last_event_at);
```

Keep `base_score` and `last_event_at` separate. The score you present is always derived
at query time using the decay formula so you never need batch recalculation jobs.

## Segment Thresholds

```typescript
function classifySegment(effectiveScore: number, daysSinceLastEvent: number): string {
  if (effectiveScore >= 50)                              return 'champion';
  if (effectiveScore >= 20 && daysSinceLastEvent <= 60) return 'active';
  if (effectiveScore >= 5  && daysSinceLastEvent <= 120) return 'at_risk';
  if (daysSinceLastEvent > 120 && daysSinceLastEvent <= 270) return 'lapsed';
  return 'dormant';
}
```

Segments and their send strategy:

| Segment   | Effective Score | Cadence            | Content             |
|-----------|-----------------|--------------------|---------------------|
| Champion  | ≥ 50            | Full cadence       | All campaigns       |
| Active    | 20–49           | Full cadence       | All campaigns       |
| At-Risk   | 5–19            | Reduced 50 %       | Re-engagement only  |
| Lapsed    | < 5, 120-270 d  | Win-back sequence  | Special offer       |
| Dormant   | < 5, > 270 d    | Suppressed         | None (sunset)       |

## Worker: Event Ingestion via Queue

ESP webhooks (Resend, SendGrid, Postmark) post event payloads to a Worker endpoint which
validates the signature and enqueues for async processing:

```typescript
// src/event-ingest.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const sig = request.headers.get('X-Resend-Signature') ?? '';
    if (!verifyHmac(sig, await request.text(), env.WEBHOOK_SECRET)) {
      return new Response('Forbidden', { status: 403 });
    }
    const events: ESPEvent[] = await request.json();
    await env.SCORE_QUEUE.sendBatch(
      events.map(e => ({ body: e, contentType: 'json' }))
    );
    return new Response('ok', { status: 202 });
  },
};
```

The Queue consumer updates scores in D1:

```typescript
// src/score-consumer.ts
const HALF_LIFE_DAYS = 90;
const LAMBDA = Math.LN2 / HALF_LIFE_DAYS;

const POINT_MAP: Record<string, number> = {
  email.opened:        2,
  email.clicked:       5,
  email.bounced.hard: -100,
  email.bounced.soft: -10,
  email.complained:   -100,
};

export default {
  async queue(batch: MessageBatch<ESPEvent>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { type, email, timestamp } = msg.body;
      const delta = POINT_MAP[type] ?? 0;
      const now = Date.parse(timestamp);

      // Decay existing base_score before adding delta
      const row = await env.DB.prepare(
        'SELECT base_score, last_event_at FROM subscriber_scores WHERE email = ?'
      ).bind(email).first<{ base_score: number; last_event_at: number }>();

      let newBase = delta;
      if (row) {
        const daysSince = (now - row.last_event_at) / 86_400_000;
        const decayed = row.base_score * Math.exp(-LAMBDA * daysSince);
        newBase = Math.max(0, decayed + delta);
      }

      const days = row ? (now - row.last_event_at) / 86_400_000 : 0;
      const effectiveScore = newBase; // already decayed above
      const segment = classifySegment(effectiveScore, days);

      await env.DB.prepare(`
        INSERT INTO subscriber_scores
          (subscriber_id, email, base_score, last_event_at, last_event_type, segment, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
          base_score      = excluded.base_score,
          last_event_at   = excluded.last_event_at,
          last_event_type = excluded.last_event_type,
          segment         = excluded.segment,
          updated_at      = excluded.updated_at
      `).bind(
        crypto.randomUUID(), email, newBase, now, type, segment, now, now
      ).run();

      msg.ack();
    }
  },
};
```

## Querying Segments for Send-Time Filtering

Before any campaign dispatch, filter the recipient list server-side:

```typescript
async function getSegmentEmails(db: D1Database, segments: string[]): Promise<string[]> {
  const placeholders = segments.map(() => '?').join(',');
  const rows = await db.prepare(
    `SELECT email FROM subscriber_scores WHERE segment IN (${placeholders})`
  ).bind(...segments).all<{ email: string }>();
  return rows.results.map(r => r.email);
}

// Champions + Active only
const recipients = await getSegmentEmails(env.DB, ['champion', 'active']);
```

## Anti-patterns

- **Counting machine opens as engagement**: Apple Mail Privacy Protection pre-fetches
  open pixels on all iOS 15+ and macOS 12+ devices. An open alone is not a reliable
  engagement signal. Weight clicks 2.5× heavier than opens, or disable open-based
  scoring entirely and rely on clicks and conversions.
- **Batch-writing effective score to DB on a cron**: storing the decayed score instead
  of the base score means every scheduled job touches every row. Store `base_score`
  and `last_event_at` only; derive effective score at query time or in a generated column.
- **Never sunsetting dormant subscribers**: keeping zero-engagement contacts inflates
  list size, increases complaint rate, and costs more per send. Apply the sunset policy
  at 270–365 days of inactivity (see `email-sunset-policy.md`).
- **Suppressing lapsed subscribers without a win-back attempt**: lapsed subscribers
  converted from a dedicated win-back campaign at 3–5× higher rate than cold acquires.
  Run two to three win-back emails before moving to dormant.

## Gotchas

- **Score floor at zero**: negative events (complaints, hard bounces) should trigger
  immediate suppression, not drive scores into large negative values that silently
  linger in the database.
- **New subscribers start at 0**: a new subscriber with zero events has the same
  default score as a dormant one. Add a `new` segment for accounts under 30 days old
  and treat them with a welcome sequence instead of the re-engagement path.
- **D1 row-level contention**: high-volume webhooks for the same email address can
  create write contention in D1. The Queue serializes processing and the UPSERT handles
  concurrent inserts safely.
- **Attribution window for conversions**: a purchase "triggered by email" requires a
  cookie or link-parameter attribution window (typically 5–7 days after click). Define
  and document the window before adding conversion scores.

## Verification

1. Send a test click event through the webhook endpoint; confirm the subscriber's
   `base_score` increases in D1 and segment transitions from `new` to `active`.
2. Manually set `last_event_at` to 180 days ago and query the derived effective score;
   confirm it is approximately 25 % of the stored `base_score` (two half-lives).
3. Send a `email.complained` event and confirm the subscriber's segment flips to
   a suppression-eligible state immediately.
4. Run `SELECT segment, COUNT(*) FROM subscriber_scores GROUP BY segment` and validate
   the distribution against expected business ratios.

## Related

- `email-sunset-policy.md`
- `suppression-list-management.md`
- `email-list-hygiene.md`
- `complaint-rate-monitoring.md`
- `email-analytics-metrics.md`

## Sources

- Litmus Email Analytics report 2024: https://www.litmus.com/email-analytics
- Apple Mail Privacy Protection impact: https://support.apple.com/en-us/HT212019
- Cloudflare D1 docs: https://developers.cloudflare.com/d1/
- Cloudflare Queues docs: https://developers.cloudflare.com/queues/
