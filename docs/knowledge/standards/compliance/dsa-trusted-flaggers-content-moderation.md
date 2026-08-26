# DSA Trusted Flaggers & Content Moderation — Workers Intake Pipeline

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

DSA Article 22 requires online platforms to give trusted flaggers a "priority" processing
path for illegal-content notices. example project receives flag submissions from both ordinary users
and DSA-awarded trusted-flagger organisations. Engineers need a concrete implementation:
registry storage, API intake, and queue prioritisation inside Cloudflare Workers.

## Context

The Digital Services Act (EU) 2022/2065 created a two-tier flagging regime:

- **Ordinary user flags** — basic notice-and-action (Art. 16); no priority obligation.
- **Trusted Flagger flags** — must be processed "with priority" (Art. 22(3)); trusted
  flagger status is awarded by Digital Services Coordinators (DSCs) in each member state.

As of 2026, EU DSCs maintain public registers of trusted flaggers (e.g. INHOPE members,
NCMEC, national police bodies, GDPR supervisory authorities for data-related violations).

example project uses Cloudflare Workers for the flag intake endpoint, D1 for the flagger registry
and queue, and Queues (or R2-backed batch) for async moderation worker dispatch.

## DSA Compliance Requirements Summary

```
+---------------------------+---------------------------+-----------------------------+
| Obligation                | Article                   | Engineering implication     |
+---------------------------+---------------------------+-----------------------------+
| Priority processing       | Art. 22(3)                | Separate high-priority queue|
| Timely feedback           | Art. 22(4)                | Status webhook / email      |
| Publish flagger list      | Art. 24 transparency rpt  | Public JSON endpoint        |
| Suspension for abuse      | Art. 22(6)                | Abuse-score column + cron   |
| Notice contents           | Art. 16(2)                | Schema validation on intake |
| Decision notification     | Art. 17                  | Outcome + reason stored     |
+---------------------------+---------------------------+-----------------------------+
```

## D1 Trusted Flagger Registry Schema

```sql
-- migrations/0015_trusted_flaggers.sql
CREATE TABLE trusted_flaggers (
  id              TEXT    PRIMARY KEY,        -- UUIDv7
  org_name        TEXT    NOT NULL,
  dsc_country     TEXT    NOT NULL,           -- ISO 3166-1 alpha-2
  dsc_reference   TEXT    NOT NULL,           -- DSC award reference number
  contact_email   TEXT    NOT NULL,
  api_key_hash    TEXT    NOT NULL UNIQUE,    -- SHA-256 of issued API key
  status          TEXT    NOT NULL DEFAULT 'active'
                          CHECK(status IN ('active','suspended','revoked')),
  abuse_score     INTEGER NOT NULL DEFAULT 0, -- incremented on bad flags
  awarded_at      INTEGER NOT NULL,
  expires_at      INTEGER,                    -- NULL = indefinite (uncommon)
  suspended_at    INTEGER,
  suspension_note TEXT,
  created_at      INTEGER NOT NULL
);

CREATE TABLE flag_notices (
  id              TEXT    PRIMARY KEY,
  flagger_id      TEXT    REFERENCES trusted_flaggers(id),  -- NULL = ordinary user
  flagger_type    TEXT    NOT NULL CHECK(flagger_type IN ('trusted','user','automated')),
  priority        INTEGER NOT NULL DEFAULT 0,  -- 1 = trusted, 0 = ordinary
  content_url     TEXT    NOT NULL,
  content_type    TEXT    NOT NULL,            -- 'post' | 'comment' | 'media'
  content_id      TEXT    NOT NULL,
  illegal_category TEXT   NOT NULL,            -- 'csam' | 'terrorism' | 'hate' | ...
  reason_text     TEXT,
  dsa_article_ref TEXT,                        -- e.g. "Art. 16 DSA"
  submitted_at    INTEGER NOT NULL,
  queued_at       INTEGER,
  processed_at    INTEGER,
  outcome         TEXT CHECK(outcome IN ('removed','kept','escalated','pending')),
  outcome_reason  TEXT,
  notified_at     INTEGER                      -- when Art. 17 notification sent
);

CREATE INDEX idx_fn_priority ON flag_notices(priority DESC, submitted_at ASC)
  WHERE outcome = 'pending';
CREATE INDEX idx_fn_flagger  ON flag_notices(flagger_id, submitted_at DESC);
```

## Workers Flag Intake Pipeline

```typescript
// workers/src/routes/flags/intake.ts
import { Env } from '../../types';

const ILLEGAL_CATEGORIES = new Set([
  'csam','terrorism','hate_speech','disinformation','counterfeit',
  'non_consensual_intimate','drug_sale','weapon_sale','fraud',
]);

interface FlagPayload {
  content_url: string;
  content_type: 'post' | 'comment' | 'media';
  content_id: string;
  illegal_category: string;
  reason_text?: string;
  dsa_article_ref?: string;
}

export async function handleFlagIntake(request: Request, env: Env): Promise<Response> {
  const apiKey = <redacted-secret>'X-Flagger-Api-Key');
  let flaggerId: string | null = null;
  let priority = 0;

  // Resolve trusted flagger
  if (apiKey) {
    const keyHash = await sha256(apiKey);
    const flagger = await env.DB.prepare(`
      SELECT id, status, abuse_score FROM trusted_flaggers
      WHERE api_key_hash = ? AND status = 'active'
    `).bind(keyHash).first<{ id: string; status: string; abuse_score: number }>();

    if (!flagger) return new Response('Unauthorized', { status: 401 });
    if (flagger.abuse_score >= 50) {
      // Auto-suspend
      await env.DB.prepare(`
        UPDATE trusted_flaggers SET status='suspended', suspended_at=?, suspension_note=?
        WHERE id=?
      `).bind(Date.now(), 'Abuse score threshold exceeded', flagger.id).run();
      return new Response('Account suspended', { status: 403 });
    }
    flaggerId = flagger.id;
    priority = 1; // DSA Art. 22 priority flag
  }

  const body = await request.json<FlagPayload>();
  if (!ILLEGAL_CATEGORIES.has(body.illegal_category)) {
    return new Response('Unknown illegal_category', { status: 422 });
  }

  const noticeId = crypto.randomUUID();
  const now = Date.now();

  await env.DB.prepare(`
    INSERT INTO flag_notices
      (id, flagger_id, flagger_type, priority, content_url, content_type,
       content_id, illegal_category, reason_text, dsa_article_ref, submitted_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).bind(
    noticeId,
    flaggerId,
    flaggerId ? 'trusted' : 'user',
    priority,
    body.content_url,
    body.content_type,
    body.content_id,
    body.illegal_category,
    body.reason_text ?? null,
    body.dsa_article_ref ?? null,
    now
  ).run();

  // Enqueue to moderation queue (priority routing)
  await env.MOD_QUEUE.send({
    noticeId,
    priority,
    contentId: body.content_id,
    category: body.illegal_category,
  }, { contentType: 'json' });

  return Response.json({ noticeId, priority, status: 'queued' }, { status: 202 });
}

async function sha256(text: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2,'0')).join('');
}
```

## Moderation Queue Routing

```typescript
// workers/src/queues/moderation-consumer.ts
export default {
  async queue(batch: MessageBatch<ModerationMessage>, env: Env): Promise<void> {
    // Sort: trusted (priority=1) first, then by submitted_at ASC
    const msgs = [...batch.messages].sort((a, b) =>
      b.body.priority - a.body.priority
    );

    for (const msg of msgs) {
      try {
        await processModerationItem(msg.body, env);
        msg.ack();
      } catch (e) {
        msg.retry({ delaySeconds: 30 });
      }
    }
  }
};

interface ModerationMessage {
  noticeId: string;
  priority: number;
  contentId: string;
  category: string;
}

async function processModerationItem(item: ModerationMessage, env: Env): Promise<void> {
  // CSAM: immediate removal + NCMEC report (no human review delay)
  if (item.category === 'csam') {
    await env.DB.prepare(`
      UPDATE flag_notices SET outcome='removed', processed_at=? WHERE id=?
    `).bind(Date.now(), item.noticeId).run();
    await notifyFlaggerOutcome(item.noticeId, 'removed', env);
    return;
  }

  // Other categories: route to human review tool via R2 task file
  await env.REVIEW_BUCKET.put(
    `queue/${item.priority === 1 ? 'trusted' : 'standard'}/${item.noticeId}.json`,
    JSON.stringify(item)
  );
}

async function notifyFlaggerOutcome(noticeId: string, outcome: string, env: Env): Promise<void> {
  // Art. 17: send decision + reason to reporter
  const notice = await env.DB.prepare(`
    SELECT fn.*, tf.contact_email FROM flag_notices fn
    LEFT JOIN trusted_flaggers tf ON fn.flagger_id = tf.id
    WHERE fn.id = ?
  `).bind(noticeId).first();

  if (notice?.contact_email) {
    // dispatch email via Email Worker / SendGrid binding
    await env.DB.prepare(
      `UPDATE flag_notices SET notified_at=? WHERE id=?`
    ).bind(Date.now(), noticeId).run();
  }
}
```

## Public Transparency Endpoint

```typescript
// GET /api/dsa/trusted-flaggers  (public, unauthenticated)
export async function listTrustedFlaggers(env: Env): Promise<Response> {
  const rows = await env.DB.prepare(`
    SELECT org_name, dsc_country, dsc_reference, status, awarded_at
    FROM trusted_flaggers WHERE status != 'revoked'
    ORDER BY org_name
  `).all();
  return Response.json({
    generated_at: new Date().toISOString(),
    dsa_article: 'Art. 24 DSA',
    flaggers: rows.results,
  });
}
```

## Anti-patterns

- Treating all flags equally in one FIFO queue — violates Art. 22(3) priority obligation.
- Storing raw API keys in D1 — always store `SHA-256(key)`.
- Never sending Art. 17 decision notifications — even "kept" decisions require a reason.
- Suspending a trusted flagger without recording `suspension_note` — DSC audits require
  documented grounds for suspension (Art. 22(6)).
- Blocking the intake response on D1 write latency — use `waitUntil` for non-critical
  writes; keep the 202 response fast.

## Gotchas

- **DSA Art. 22(2) requires a specific application process** — do not self-designate
  organisations as trusted flaggers; only DSC awards count.
- **Expiry**: some DSC awards have an expiry date; the cron job must check `expires_at`
  and downgrade to `revoked` automatically.
- **Cross-border**: a trusted flagger awarded by the German DSC is valid EU-wide; do not
  restrict to country of award in the queue routing logic.
- **Volume spikes**: a trusted flagger sending thousands of flags per minute may
  indicate automation abuse — rate-limit per `flagger_id` separately from ordinary users.
- **CSAM mandatory reporting**: NCMEC reporting under EU CSAR Regulation is separate from
  DSA; do not conflate the two pipelines.

## Verification

```bash
# Check trusted flagger is active
wrangler d1 execute example project-prod \
  --command "SELECT org_name, status, abuse_score FROM trusted_flaggers;"

# Confirm priority queue has items ahead of standard queue
wrangler d1 execute example project-prod \
  --command "SELECT flagger_type, priority, COUNT(*) cnt FROM flag_notices
             WHERE outcome='pending' GROUP BY priority ORDER BY priority DESC;"

# List R2 review objects by priority lane
wrangler r2 object list example project-review-bucket --prefix "queue/trusted/"
wrangler r2 object list example project-review-bucket --prefix "queue/standard/"

# Verify Art. 17 notifications are being sent (notified_at set within 24h of processed_at)
wrangler d1 execute example project-prod \
  --command "SELECT id, outcome, processed_at, notified_at,
             (notified_at - processed_at)/1000 AS lag_seconds
             FROM flag_notices WHERE outcome != 'pending' ORDER BY processed_at DESC LIMIT 20;"
```

## Related

- `dsa-online-platform-obligations-2026.md`
- `csam-detection-ncmec-reporting-plumbing.md`
- `dmca-takedown-automation-plumbing.md`
- `eu-terrorist-content-removal-order-operations.md`
- `audit-log-mandatory.md`

## Sources

- DSA (EU) 2022/2065, Art. 16, 17, 22, 24
- EDPB DSA Q&A guidance (2024)
- Cloudflare Queues documentation — developers.cloudflare.com/queues
- Cloudflare D1 documentation — developers.cloudflare.com/d1
- INHOPE trusted-flagger programme — inhope.org
