# Bulk Email Warming Strategy for New Domains

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A new sending domain with no historical reputation is rejected or deferred by Gmail, Yahoo, and Microsoft even when SPF, DKIM, and DMARC are correctly configured. Bulk senders that migrate to a new domain or launch a new product line experience 80–90% inbox placement failure in the first week because receiver reputation systems have no positive signal for the domain. A structured warming schedule — ramping from low volumes to full scale over 4–8 weeks while monitoring complaint rates, bounce rates, and Google Postmaster Domain Reputation signals — is required before the domain can reliably deliver at scale.

## Context

Inbox providers use domain reputation (distinct from IP reputation since the 2019–2020 era) to classify inbound email. A new domain starts at "neutral" reputation and must accumulate positive engagement signals (opens, replies, and "not spam" moves) before Gmail's domain reputation rises from neutral to low, medium, and ultimately high. Sending too much volume too soon with any complaints causes the domain to be classified as "bad" reputation, which is very difficult to recover from. The warming schedule must be paired with list hygiene — sending only to highly-engaged, recently-acquired addresses during the early phases — because a complaint rate above 0.10% (Google's threshold) during warming can permanently damage the domain's standing with major providers.

## Phase Schedule

### Phase 1 — Seeding (Days 1–7): 50–500 messages/day

Send exclusively to:
- Internal company email addresses
- Known personal contacts who expect email
- Seed accounts (real inboxes you control at Gmail, Outlook, Yahoo, iCloud)

Seed accounts must open, reply to, and star messages to generate positive engagement. Do not include any marketing content.

### Phase 2 — Early Ramp (Days 8–21): 500–5,000 messages/day

Send to your most engaged segment — subscribers who opened or clicked within the last 30 days. Volume doubles every 2–3 days if complaint rate stays below 0.05% and bounce rate below 1%.

### Phase 3 — Growth (Days 22–42): 5,000–100,000 messages/day

Expand to subscribers active within 90 days. Continue doubling every 3 days. Begin monitoring Google Postmaster Domain Reputation and Microsoft SNDS data.

### Phase 4 — Scale (Day 43+): Full volume

Include all clean, consented subscribers. Maintain complaint rate < 0.08% and bounce rate < 2%.

## Cloudflare Worker — Volume Gate

A Worker that enforces the daily sending cap and tracks accumulated send counts against the warming schedule using KV:

```typescript
// src/warming-gate.ts
export interface Env {
  KV:           KVNamespace;
  DB:           D1Database;
  EMAIL_QUEUE:  Queue;
}

interface WarmingPhase {
  startDay:   number;
  endDay:     number;
  dailyCap:   number;
  maxBounceRate: number;   // fraction, e.g. 0.01
  maxComplaintRate: number;
}

const WARMING_SCHEDULE: WarmingPhase[] = [
  { startDay:  1, endDay:  7,  dailyCap:     500, maxBounceRate: 0.01, maxComplaintRate: 0.001 },
  { startDay:  8, endDay: 14,  dailyCap:    2000, maxBounceRate: 0.01, maxComplaintRate: 0.001 },
  { startDay: 15, endDay: 21,  dailyCap:    5000, maxBounceRate: 0.01, maxComplaintRate: 0.001 },
  { startDay: 22, endDay: 28,  dailyCap:   15000, maxBounceRate: 0.015, maxComplaintRate: 0.0008 },
  { startDay: 29, endDay: 35,  dailyCap:   40000, maxBounceRate: 0.015, maxComplaintRate: 0.0008 },
  { startDay: 36, endDay: 42,  dailyCap:  100000, maxBounceRate: 0.02, maxComplaintRate: 0.001 },
  { startDay: 43, endDay: 999, dailyCap: 9999999, maxBounceRate: 0.02, maxComplaintRate: 0.001 },
];

export async function getDailyPhase(kv: KVNamespace, domain: string): Promise<WarmingPhase> {
  const startStr = await kv.get(`warming:${domain}:start_epoch`);
  const startEpoch = startStr ? Number(startStr) : Math.floor(Date.now() / 1000);
  if (!startStr) {
    await kv.put(`warming:${domain}:start_epoch`, String(startEpoch));
  }
  const dayNumber = Math.floor((Date.now() / 1000 - startEpoch) / 86400) + 1;
  const phase = WARMING_SCHEDULE.find(p => dayNumber >= p.startDay && dayNumber <= p.endDay);
  return phase ?? WARMING_SCHEDULE[WARMING_SCHEDULE.length - 1];
}

export async function checkAndIncrementSendCount(
  kv: KVNamespace,
  domain: string,
  count: number
): Promise<{ allowed: boolean; remaining: number }> {
  const dateKey = new Date().toISOString().slice(0, 10);   // YYYY-MM-DD
  const kvKey   = `warming:${domain}:sends:${dateKey}`;
  const phase   = await getDailyPhase(kv, domain);

  const current = Number(await kv.get(kvKey) ?? '0');
  if (current + count > phase.dailyCap) {
    return { allowed: false, remaining: Math.max(0, phase.dailyCap - current) };
  }
  await kv.put(kvKey, String(current + count), { expirationTtl: 172800 }); // 48 h TTL
  return { allowed: true, remaining: phase.dailyCap - current - count };
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const { domain, messages } = await req.json<{
      domain: string;
      messages: Array<{ to: string; subject: string; html: string }>;
    }>();

    const gate = await checkAndIncrementSendCount(env.KV, domain, messages.length);
    if (!gate.allowed) {
      return Response.json({
        status: 'rate_limited',
        queued: 0,
        remainingToday: gate.remaining,
      }, { status: 429 });
    }

    // Check current health metrics before dispatching
    const health = await getWarmingHealth(env.DB, domain);
    const phase  = await getDailyPhase(env.KV, domain);

    if (health.bounce_rate > phase.maxBounceRate) {
      return Response.json({
        status: 'warming_paused',
        reason: `Bounce rate ${(health.bounce_rate * 100).toFixed(2)}% exceeds phase threshold`,
      }, { status: 503 });
    }
    if (health.complaint_rate > phase.maxComplaintRate) {
      return Response.json({
        status: 'warming_paused',
        reason: `Complaint rate ${(health.complaint_rate * 100).toFixed(3)}% exceeds phase threshold`,
      }, { status: 503 });
    }

    for (const msg of messages) {
      await env.EMAIL_QUEUE.send({ domain, ...msg });
    }

    return Response.json({ status: 'queued', count: messages.length, remaining: gate.remaining });
  },
};

async function getWarmingHealth(
  db: D1Database,
  domain: string
): Promise<{ bounce_rate: number; complaint_rate: number }> {
  const since = Math.floor(Date.now() / 1000) - 7 * 86400;   // last 7 days
  const row = await db.prepare(`
    SELECT
      CAST(SUM(bounces)    AS REAL) / NULLIF(SUM(sends), 0) AS bounce_rate,
      CAST(SUM(complaints) AS REAL) / NULLIF(SUM(sends), 0) AS complaint_rate
    FROM warming_daily_stats
    WHERE domain = ? AND date_epoch >= ?
  `).bind(domain, since).first<{ bounce_rate: number; complaint_rate: number }>();
  return row ?? { bounce_rate: 0, complaint_rate: 0 };
}
```

## D1 Schema — Warming Metrics

```sql
-- migrations/0001_warming.sql

CREATE TABLE IF NOT EXISTS warming_daily_stats (
  domain        TEXT NOT NULL,
  date_epoch    INTEGER NOT NULL,     -- midnight UTC epoch for the day
  sends         INTEGER NOT NULL DEFAULT 0,
  deliveries    INTEGER NOT NULL DEFAULT 0,
  bounces       INTEGER NOT NULL DEFAULT 0,
  complaints    INTEGER NOT NULL DEFAULT 0,
  opens         INTEGER NOT NULL DEFAULT 0,
  clicks        INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (domain, date_epoch)
);

CREATE TABLE IF NOT EXISTS warming_events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  domain      TEXT NOT NULL,
  event_type  TEXT NOT NULL,    -- 'send' | 'delivery' | 'bounce' | 'complaint' | 'open' | 'click'
  bounce_type TEXT,             -- 'hard' | 'soft' | null
  message_id  TEXT,
  recipient   TEXT,
  occurred_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_warming_domain_event ON warming_events (domain, event_type, occurred_at DESC);
```

## Worker — Webhook Ingest (ESP Events)

```typescript
// src/warming-webhook.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== 'POST') return new Response('', { status: 405 });

    const events: Array<{ event: string; domain: string; timestamp: number; email?: string }> =
      await req.json();

    const TODAY = Math.floor(new Date().setUTCHours(0, 0, 0, 0) / 1000);

    const updates: Record<string, Partial<Record<
      'sends' | 'deliveries' | 'bounces' | 'complaints' | 'opens' | 'clicks', number
    >>> = {};

    for (const ev of events) {
      const key = ev.domain;
      updates[key] = updates[key] ?? {};
      const u = updates[key];

      switch (ev.event) {
        case 'delivered':   u.deliveries  = (u.deliveries  ?? 0) + 1; break;
        case 'bounce':
        case 'hard_bounce': u.bounces     = (u.bounces     ?? 0) + 1; break;
        case 'spam_report': u.complaints  = (u.complaints  ?? 0) + 1; break;
        case 'open':        u.opens       = (u.opens       ?? 0) + 1; break;
        case 'click':       u.clicks      = (u.clicks      ?? 0) + 1; break;
      }
    }

    const stmts = Object.entries(updates).map(([domain, delta]) => {
      const cols = Object.keys(delta).join(', ');
      const incs = Object.entries(delta).map(([c, n]) => `${c} = ${c} + ${n}`).join(', ');
      return env.DB.prepare(`
        INSERT INTO warming_daily_stats (domain, date_epoch, ${cols})
        VALUES (?, ?, ${Object.values(delta).join(', ')})
        ON CONFLICT (domain, date_epoch) DO UPDATE SET ${incs}
      `).bind(domain, TODAY);
    });

    await env.DB.batch(stmts);
    return new Response(null, { status: 204 });
  },
};
```

## Segment Selection Strategy

| Warming Phase | Allowed Segments                                 |
|---------------|--------------------------------------------------|
| Phase 1       | Internal seed addresses only                     |
| Phase 2       | Opened/clicked in last 30 days                   |
| Phase 3       | Opened/clicked in last 90 days                   |
| Phase 4       | All clean (validated, non-suppressed) subscribers |

### Engagement-first Sorting Query

```sql
-- Pick top N most-engaged subscribers for each daily batch
SELECT u.id, u.email
FROM users u
JOIN email_engagement e ON e.user_id = u.id
WHERE e.last_open_at >= unixepoch() - (? * 86400)   -- phase engagement window
  AND u.opted_in = 1
  AND u.bounced  = 0
ORDER BY e.last_open_at DESC
LIMIT ?;
```

## Monitoring Checklist

- **Google Postmaster Tools**: check Domain Reputation daily during phases 1–2; weekly during phase 3+. Any drop to "bad" requires an immediate 3-day pause.
- **Microsoft SNDS (Smart Network Data Services)**: check IP complaint rate; green (< 0.3%), yellow (0.3–10%), red (> 10%).
- **Bounce rate**: hard bounces > 1% → pause and run list hygiene. Soft bounce spikes typically indicate reputation throttling.
- **Complaint rate**: > 0.08% on any single day → pause sending for 48 hours and review content and segment.
- **Spam trap hits**: use an inbox placement seed list service (e.g. 250ok, GlockApps) to detect spam-trap addresses before they reach live sends.

## Mobile vs Desktop Email Rendering Considerations

During warming, send simplified, text-heavy emails to maximise engagement signal quality:

- **Responsive single-column HTML**: avoids rendering issues that cause recipients to delete without opening, which generates a negative signal.
- **No images in Phase 1**: images blocked by default in Outlook desktop inflate "no-open" counts. Text-only or inline-text-first content registers opens from pixel-blocking clients only if the image tracking pixel loads — skip tracking pixels in Phase 1 to avoid inflated open counts from Apple MPP.
- **Short subject lines**: ≤ 40 chars to avoid clipping on iOS lock-screen notifications; recipients who swipe-to-preview on mobile without opening still generate a positive engagement signal in some providers' models.
- **Plain-text multipart**: always include a `text/plain` part. Corporate spam filters score multipart messages higher than HTML-only; this is especially important during early warming when reputation is neutral.

## Anti-patterns

- **Sending to a full purchased list immediately**: purchased lists have unknown engagement history and guaranteed spam traps; using them during warming permanently damages the new domain.
- **Ignoring soft bounces**: repeated soft bounces (deferral 421/450) are the receiving server throttling you due to reputation concerns — they signal you must slow down, not retry at full speed.
- **Mixing new domain sends with transactional mail**: if a user's password-reset email goes through the warming domain and fails due to reputation, the business impact is severe. Warm the marketing domain separately from the transactional domain.
- **Reusing a previously suspended domain**: blacklist removal and DMARC reset do not restore receiver reputation history; a domain with prior suspension should be treated as worse-than-new.
- **Accelerating the ramp based on deliveries alone**: delivery to the spam folder counts as a "delivery" in most ESP bounce reporting. Use inbox placement seed tests, not raw delivery rates, to confirm warming progress.

## Gotchas

- KV `expirationTtl` is relative to the put time, not midnight UTC. For a per-day counter, set TTL to 48 hours to handle timezone edge cases and delayed writes.
- Google Postmaster Tools updates Domain Reputation with a ~48-hour lag. A reputation drop visible today reflects sending behaviour from 2 days ago.
- Some ESP webhooks fire `bounce` for both hard and soft bounces under different event names — map carefully to avoid inflating hard bounce counts with soft deferrals.
- The warming schedule must be maintained even if the daily cap is not reached. Sending 100 messages on day 1 and then skipping to 50,000 on day 5 without filling the intermediate days breaks the gradual ramp signal.

## Verification

```bash
# Check current warming phase and remaining daily capacity
curl https://your-worker.workers.dev/warming/status \
  -H 'X-Domain: newdomain.com'

# View 7-day rolling health
npx wrangler d1 execute DB --command \
  "SELECT date(date_epoch, 'unixepoch') as day,
          sends, bounces, complaints,
          ROUND(100.0*bounces/NULLIF(sends,0),2) AS bounce_pct,
          ROUND(100.0*complaints/NULLIF(sends,0),3) AS complaint_pct
   FROM warming_daily_stats WHERE domain='newdomain.com'
   ORDER BY date_epoch DESC LIMIT 7;"

# Google Postmaster domain reputation (check in Postmaster Tools UI)
# Or via the Postmaster Tools API if enrolled
curl "https://gmailpostmastertools.googleapis.com/v1/domains/newdomain.com/trafficStats" \
  -H "Authorization: Bearer $POSTMASTER_TOKEN"
```

## Related

- `domain-warming-strategy.md`
- `ip-warming-strategy.md`
- `ip-warming-domain-reputation-deliverability.md`
- `complaint-rate-monitoring.md`
- `email-blocklist-remediation.md`
- `google-postmaster-setup.md`
- `microsoft-snds-setup.md`
- `email-list-hygiene.md`
- `spamtrap-types-avoidance.md`

## Sources

- Google Postmaster Tools — https://postmaster.google.com/
- Google Bulk Sender Guidelines — https://support.google.com/mail/answer/81126
- Microsoft SNDS — https://sendersupport.olc.protection.outlook.com/snds/
- RFC 5321 — SMTP enhanced status codes for deferrals (4xx)
- Validity (formerly Return Path) Domain Warming Best Practices — https://validity.com/
