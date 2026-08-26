# Email Domain Warmup with IP Pool Rotation via Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A new sending domain or dedicated IP pool begins with zero reputation. Blasting full volume on day one triggers spam filters and causes ISPs to block the entire pool. A warmup schedule ramps volume daily while rotating IPs so no single IP carries all the risk. Cloudflare Workers orchestrate pool selection, enforce per-IP daily caps, and record send telemetry in D1.

---

## Context

Most ESPs expose IP pool selection via an API header or sub-account routing. Cloudflare Workers sit in front of the ESP API call: they read the current warmup schedule from D1, select the appropriate IP pool, enforce the daily volume cap, and forward the send request. A cron Worker advances the schedule each day and resets counters.

This pattern assumes a multi-pool ESP (e.g. Mailgun, Postmark, or self-managed Haraka/Postal) where pool IDs can be specified per message. The Worker is the single point of pool selection logic.

---

## D1 Schema

```sql
CREATE TABLE ip_pools (
  pool_id       TEXT PRIMARY KEY,         -- e.g. 'warmup-pool-a'
  provider_tag  TEXT NOT NULL,            -- ESP-specific pool identifier
  daily_cap     INTEGER NOT NULL,         -- max sends per day during warmup
  warmup_day    INTEGER NOT NULL DEFAULT 1,
  status        TEXT NOT NULL DEFAULT 'warming'
                CHECK(status IN ('warming','warm','paused','retired')),
  created_at    INTEGER NOT NULL
);

-- Standard warmup schedule: day → max sends
CREATE TABLE warmup_schedule (
  day           INTEGER PRIMARY KEY,
  max_sends     INTEGER NOT NULL
);

-- Running counters, reset daily by cron
CREATE TABLE pool_daily_counters (
  pool_id       TEXT NOT NULL,
  date_utc      TEXT NOT NULL,            -- 'YYYY-MM-DD'
  sends_today   INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (pool_id, date_utc)
);

-- Compact send log for compliance and analysis
CREATE TABLE warmup_send_log (
  id            TEXT PRIMARY KEY,
  pool_id       TEXT NOT NULL,
  recipient_domain TEXT NOT NULL,
  sent_at       INTEGER NOT NULL,
  message_id    TEXT
);
```

Pre-populate the warmup schedule (standard ISP ramp):

```sql
INSERT INTO warmup_schedule VALUES
  (1, 50), (2, 100), (3, 200), (4, 500), (5, 1000),
  (6, 2000), (7, 5000), (8, 10000), (9, 20000), (10, 40000),
  (11, 70000), (12, 100000), (13, 150000), (14, 200000);
```

---

## Pool Selection Logic

```typescript
// src/pool-selector.ts
import { Env } from './types';
import { ulid } from 'ulid';

interface PoolSelection {
  poolId: string;
  providerTag: string;
}

export async function selectPool(
  env: Env,
  recipientDomain: string
): Promise<PoolSelection> {
  const todayUtc = new Date().toISOString().slice(0, 10);

  // Find a warming pool that still has daily capacity
  const pool = await env.DB.prepare(`
    SELECT
      p.pool_id,
      p.provider_tag,
      p.warmup_day,
      COALESCE(c.sends_today, 0) AS sends_today,
      s.max_sends
    FROM ip_pools p
    JOIN warmup_schedule s ON s.day = p.warmup_day
    LEFT JOIN pool_daily_counters c
      ON c.pool_id = p.pool_id AND c.date_utc = ?
    WHERE p.status = 'warming'
      AND COALESCE(c.sends_today, 0) < s.max_sends
    ORDER BY RANDOM()    -- rotate randomly among eligible pools
    LIMIT 1
  `).bind(todayUtc).first<{
    pool_id: string;
    provider_tag: string;
    warmup_day: number;
    sends_today: number;
    max_sends: number;
  }>();

  if (!pool) {
    // All warming pools at cap — fall back to warm (fully ramped) pool
    const warmPool = await env.DB.prepare(`
      SELECT pool_id, provider_tag FROM ip_pools WHERE status = 'warm' LIMIT 1
    `).first<{ pool_id: string; provider_tag: string }>();

    if (!warmPool) throw new Error('No available IP pool');
    return { poolId: warmPool.pool_id, providerTag: warmPool.provider_tag };
  }

  return { poolId: pool.pool_id, providerTag: pool.provider_tag };
}

export async function recordSend(
  env: Env,
  poolId: string,
  recipientDomain: string,
  messageId: string
): Promise<void> {
  const todayUtc = new Date().toISOString().slice(0, 10);
  const now = Date.now();

  await env.DB.batch([
    env.DB.prepare(`
      INSERT INTO pool_daily_counters (pool_id, date_utc, sends_today)
      VALUES (?, ?, 1)
      ON CONFLICT (pool_id, date_utc) DO UPDATE SET sends_today = sends_today + 1
    `).bind(poolId, todayUtc),

    env.DB.prepare(`
      INSERT INTO warmup_send_log (id, pool_id, recipient_domain, sent_at, message_id)
      VALUES (?, ?, ?, ?, ?)
    `).bind(ulid(), poolId, recipientDomain, now, messageId),
  ]);
}
```

---

## Send Proxy Worker

```typescript
// src/send-proxy.ts
import { selectPool, recordSend } from './pool-selector';
import { Env } from './types';

interface SendPayload {
  to: string;
  subject: string;
  html: string;
  text: string;
}

export async function proxySend(
  env: Env,
  payload: SendPayload
): Promise<void> {
  const recipientDomain = payload.to.split('@')[1]?.toLowerCase() ?? 'unknown';
  const { poolId, providerTag } = await selectPool(env, recipientDomain);

  // Call ESP API with pool-specific header (Mailgun example)
  const res = await fetch('https://api.mailgun.net/v3/example.com/messages', {
    method: 'POST',
    headers: {
      Authorization: `Basic ${btoa(`api:${env.MAILGUN_API_KEY}`)}`,
      'Content-Type': 'application/x-www-form-urlencoded',
      'X-Mailgun-IP-Pool': providerTag,  // Mailgun-specific pool header
    },
    body: new URLSearchParams({
      from: `noreply@example.com`,
      to: payload.to,
      subject: payload.subject,
      html: payload.html,
      text: payload.text,
    }),
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`ESP send failed [${res.status}]: ${body}`);
  }

  const json = await res.json<{ id: string }>();
  await recordSend(env, poolId, recipientDomain, json.id);
}
```

---

## Daily Cron: Advance Warmup Day and Detect Graduation

```typescript
// src/cron.ts — scheduled daily at 00:05 UTC
export async function advanceWarmupSchedule(env: Env): Promise<void> {
  const yesterday = new Date();
  yesterday.setUTCDate(yesterday.getUTCDate() - 1);
  const yday = yesterday.toISOString().slice(0, 10);

  // Fetch yesterday's counters for all warming pools
  const pools = await env.DB.prepare(`
    SELECT
      p.pool_id, p.warmup_day, p.daily_cap,
      COALESCE(c.sends_today, 0) AS sends_yesterday,
      s.max_sends
    FROM ip_pools p
    JOIN warmup_schedule s ON s.day = p.warmup_day
    LEFT JOIN pool_daily_counters c ON c.pool_id = p.pool_id AND c.date_utc = ?
    WHERE p.status = 'warming'
  `).bind(yday).all<{
    pool_id: string;
    warmup_day: number;
    sends_yesterday: number;
    max_sends: number;
  }>();

  const MAX_WARMUP_DAY = 14;

  for (const pool of pools.results) {
    const utilizationRate = pool.sends_yesterday / pool.max_sends;

    if (utilizationRate < 0.5) {
      // Underutilized: do not advance — repeat today's day
      continue;
    }

    const nextDay = pool.warmup_day + 1;

    if (nextDay > MAX_WARMUP_DAY) {
      // Pool has graduated: mark as warm
      await env.DB.prepare(`
        UPDATE ip_pools SET status = 'warm', warmup_day = ? WHERE pool_id = ?
      `).bind(MAX_WARMUP_DAY, pool.pool_id).run();
    } else {
      await env.DB.prepare(`
        UPDATE ip_pools SET warmup_day = ? WHERE pool_id = ?
      `).bind(nextDay, pool.pool_id).run();
    }
  }
}
```

---

## Complaint / Bounce Circuit Breaker

```typescript
// src/circuit-breaker.ts — called by FBL webhook handler
export async function checkAndPausePool(
  env: Env,
  poolId: string
): Promise<void> {
  const todayUtc = new Date().toISOString().slice(0, 10);

  // Bounce rate: compare last 4 hours to sends
  const stats = await env.DB.prepare(`
    SELECT
      COUNT(*) FILTER (WHERE sent_at > ? - 14400000) AS recent_sends
    FROM warmup_send_log WHERE pool_id = ?
  `).bind(Date.now(), poolId).first<{ recent_sends: number }>();

  // If bounce rate high (fetched from bounce table), pause pool
  const PAUSE_BOUNCE_RATE = 0.05; // 5% — very conservative during warmup
  const bounceCount = await getBounceCount(env, poolId, 14400000);

  if (stats && stats.recent_sends > 0) {
    const bounceRate = bounceCount / stats.recent_sends;
    if (bounceRate > PAUSE_BOUNCE_RATE) {
      await env.DB.prepare(`
        UPDATE ip_pools SET status = 'paused' WHERE pool_id = ?
      `).bind(poolId).run();
      console.error(`Pool ${poolId} paused: bounce rate ${(bounceRate * 100).toFixed(1)}%`);
    }
  }
}
```

---

## Anti-patterns

- **Warming a pool by sending to low-engagement lists** — ISPs track engagement (opens, clicks) during warmup; sending to cold or purchased lists produces the opposite of the intended reputation signal.
- **Jumping warmup days to catch up** — if volume targets are missed, repeating the current day is safer than advancing; overshoot triggers the same blocks you are trying to avoid.
- **Sharing a warming pool with transactional sends** — transactional emails have high engagement and no complaints; mixing them with bulk marketing distorts the pool's reputation signal.
- **Not separating pools by sending domain** — a shared IP pool used by multiple domains means one domain's spam complaints harm all others on the same pool.

---

## Gotchas

- `RANDOM()` in D1 does a full table scan on `ip_pools` — add `WHERE status = 'warming'` to limit candidates before the random order.
- Mailgun IP pool headers differ from Postmark's `X-PM-Message-Stream`; abstract the ESP-specific header behind the `providerTag` concept.
- Daily counters must reset at midnight UTC, not midnight local time; the cron and counter key must both use UTC dates.
- During warmup, prioritize sending to known-engaged recipients (recent openers) at major ISPs (Gmail, Outlook, Yahoo) — ISP reputation engines weight postmaster-domain traffic most heavily.

---

## Verification

```bash
# Check pool status and day
wrangler d1 execute DB --command \
  "SELECT pool_id, warmup_day, status FROM ip_pools"

# Check today's counters
wrangler d1 execute DB --command \
  "SELECT * FROM pool_daily_counters WHERE date_utc = date('now')"

# Simulate a send
curl -X POST https://workers.example.com/send \
  -H "Content-Type: application/json" \
  -d '{"to":"alice@gmail.com","subject":"Test","html":"<p>Hi</p>","text":"Hi"}'

# Manually trigger warmup advancement
curl -X POST https://workers.example.com/cron/advance-warmup \
  -H "X-Cron-Secret: $CRON_SECRET"

# View send log
wrangler d1 execute DB --command \
  "SELECT pool_id, recipient_domain, COUNT(*) AS sends FROM warmup_send_log GROUP BY pool_id, recipient_domain"
```

---

## Related

- `domain-warming-strategy.md`
- `ip-warming-strategy.md`
- `email-warm-up-cron-workers-schedule.md`
- `bulk-email-warming-new-domain-strategy.md`
- `dedicated-ip-vs-shared.md`
- `email-esp-failover-health-check-workers.md`
- `email-bounce-storm-circuit-breaker-workers.md`

---

## Sources

- Mailgun IP Pools: https://documentation.mailgun.com/docs/mailgun/user-manual/sending-ips/
- Postmark Message Streams: https://postmarkapp.com/developer/api/message-streams-api
- Word to the Wise IP warmup guide: https://wordtothewise.com/2014/08/ip-warming/
- Cloudflare D1 batch: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- Cloudflare Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
