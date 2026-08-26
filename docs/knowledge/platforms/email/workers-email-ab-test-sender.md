# Email A/B Testing Framework with Workers + D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You want to split-test email subject lines, sender names, or body content variants across a recipient list, track open and click rates per variant, and automatically determine a winner — all without a third-party ESP A/B feature. The system must also detect statistical significance before declaring a winner.

## Context

A Cloudflare Worker acts as the send controller. Experiment definitions and per-recipient variant assignments are stored in D1. Open tracking uses a 1-pixel tracking image served by a separate Worker route. Click tracking redirects through a Worker endpoint before forwarding the user to the real URL. Winner determination runs on-demand or on a cron trigger.

## Solution

### D1 Schema

```sql
-- migrations/0003_ab_test.sql
CREATE TABLE IF NOT EXISTS ab_experiments (
  id              TEXT PRIMARY KEY,           -- e.g. "exp-2026-q3-onboarding"
  name            TEXT NOT NULL,
  status          TEXT NOT NULL DEFAULT 'active', -- active | paused | concluded
  winner_variant  TEXT,
  created_at      INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS ab_variants (
  experiment_id   TEXT NOT NULL REFERENCES ab_experiments(id),
  variant_id      TEXT NOT NULL,              -- 'A' | 'B' | 'C'
  subject         TEXT NOT NULL,
  from_name       TEXT NOT NULL,
  html_template   TEXT NOT NULL,
  weight          REAL NOT NULL DEFAULT 0.5,  -- allocation fraction (must sum to 1)
  PRIMARY KEY (experiment_id, variant_id)
);

CREATE TABLE IF NOT EXISTS ab_sends (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  experiment_id   TEXT NOT NULL,
  variant_id      TEXT NOT NULL,
  recipient_email TEXT NOT NULL,
  sent_at         INTEGER NOT NULL DEFAULT (unixepoch()),
  opened_at       INTEGER,
  clicked_at      INTEGER,
  UNIQUE (experiment_id, recipient_email)
);

CREATE INDEX IF NOT EXISTS idx_sends_exp_variant
  ON ab_sends (experiment_id, variant_id);
```

### Worker – Send Controller

```typescript
// src/ab-test-sender.ts
import { Env } from './types';

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const { method } = req;

    if (method === 'POST' && url.pathname === '/ab/send')
      return handleSend(req, env);
    if (method === 'GET'  && url.pathname === '/ab/open')
      return handleOpenPixel(req, env);
    if (method === 'GET'  && url.pathname === '/ab/click')
      return handleClick(req, env);
    if (method === 'GET'  && url.pathname === '/ab/stats')
      return handleStats(req, env);
    if (method === 'POST' && url.pathname === '/ab/winner')
      return handleDetermineWinner(req, env);

    return new Response('Not found', { status: 404 });
  },
};

interface SendRequest {
  experimentId: string;
  recipients:   string[];
}

async function handleSend(req: Request, env: Env): Promise<Response> {
  const body: SendRequest = await req.json();
  const { experimentId, recipients } = body;

  const variants = await getVariants(env, experimentId);
  if (!variants.length) return new Response('Experiment not found', { status: 404 });

  let sent = 0, skipped = 0;
  for (const email of recipients) {
    const variant = assignVariant(email, variants);

    // Skip if already sent (idempotent)
    const existing = await env.DB.prepare(`
      SELECT 1 FROM ab_sends WHERE experiment_id=? AND recipient_email=?
    `).bind(experimentId, email).first();
    if (existing) { skipped++; continue; }

    await sendVariantEmail(env, experimentId, variant, email);

    await env.DB.prepare(`
      INSERT INTO ab_sends (experiment_id, variant_id, recipient_email)
      VALUES (?, ?, ?)
    `).bind(experimentId, variant.variant_id, email).run();

    sent++;
  }

  return Response.json({ sent, skipped });
}

function assignVariant(
  email: string,
  variants: AbVariant[]
): AbVariant {
  // Deterministic assignment: hash the email so the same recipient
  // always gets the same variant across retries
  let hash = 0;
  for (let i = 0; i < email.length; i++) {
    hash = (Math.imul(31, hash) + email.charCodeAt(i)) | 0;
  }
  const r = (Math.abs(hash) % 10000) / 10000; // 0 – 0.9999

  let cumulative = 0;
  for (const v of variants) {
    cumulative += v.weight;
    if (r < cumulative) return v;
  }
  return variants[variants.length - 1];
}

async function sendVariantEmail(
  env: Env,
  experimentId: string,
  variant: AbVariant,
  recipientEmail: string
): Promise<void> {
  const trackingId = btoa(`${experimentId}:${recipientEmail}`);
  const pixel      = `https://<worker>.workers.dev/ab/open?t=${encodeURIComponent(trackingId)}`;
  const html       = variant.html_template
    .replace('{{TRACKING_PIXEL}}', `<img  width="1" height="1" alt="" />`)
    .replace(/]+)"/g, (_, link) => {
      const clickUrl = `https://<worker>.workers.dev/ab/click?t=${encodeURIComponent(trackingId)}&u=${encodeURIComponent(link)}`;
      return ``;
    });

  const payload = {
    personalizations: [{ to: [{ email: recipientEmail }] }],
    from: { email: 'hello@example.com', name: variant.from_name },
    subject: variant.subject,
    content: [{ type: 'text/html', value: html }],
  };

  const res = await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!res.ok) throw new Error(`MailChannels ${res.status}: ${await res.text()}`);
}

async function handleOpenPixel(req: Request, env: Env): Promise<Response> {
  const t = new URL(req.url).searchParams.get('t');
  if (t) {
    const [experimentId, email] = atob(t).split(':');
    await env.DB.prepare(`
      UPDATE ab_sends SET opened_at = unixepoch()
      WHERE experiment_id=? AND recipient_email=? AND opened_at IS NULL
    `).bind(experimentId, email).run();
  }
  // Return 1x1 transparent GIF
  const gif = new Uint8Array([71,73,70,56,57,97,1,0,1,0,0,255,0,44,0,0,0,0,1,0,1,0,0,2,0,59]);
  return new Response(gif, { headers: { 'Content-Type': 'image/gif', 'Cache-Control': 'no-store' } });
}

async function handleClick(req: Request, env: Env): Promise<Response> {
  const url  = new URL(req.url);
  const t    = url.searchParams.get('t');
  const dest = url.searchParams.get('u');

  if (t) {
    const [experimentId, email] = atob(t).split(':');
    await env.DB.prepare(`
      UPDATE ab_sends SET clicked_at = unixepoch()
      WHERE experiment_id=? AND recipient_email=? AND clicked_at IS NULL
    `).bind(experimentId, email).run();
  }
  return Response.redirect(dest ?? 'https://example.com', 302);
}

async function handleStats(req: Request, env: Env): Promise<Response> {
  const expId = new URL(req.url).searchParams.get('exp');
  if (!expId) return new Response('Missing exp', { status: 400 });

  const { results } = await env.DB.prepare(`
    SELECT
      variant_id,
      COUNT(*)                                   AS sends,
      SUM(CASE WHEN opened_at  IS NOT NULL THEN 1 ELSE 0 END) AS opens,
      SUM(CASE WHEN clicked_at IS NOT NULL THEN 1 ELSE 0 END) AS clicks
    FROM ab_sends
    WHERE experiment_id = ?
    GROUP BY variant_id
  `).bind(expId).all();

  return Response.json(results);
}

async function handleDetermineWinner(req: Request, env: Env): Promise<Response> {
  const { experimentId, metric = 'clicks' }: { experimentId: string; metric?: string } = await req.json();

  const { results } = await env.DB.prepare(`
    SELECT variant_id,
           COUNT(*) AS n,
           SUM(CASE WHEN opened_at  IS NOT NULL THEN 1 ELSE 0 END) AS opens,
           SUM(CASE WHEN clicked_at IS NOT NULL THEN 1 ELSE 0 END) AS clicks
    FROM ab_sends WHERE experiment_id=? GROUP BY variant_id
  `).bind(experimentId).all<AbStats>();

  if (results.length < 2) return Response.json({ error: 'Need at least 2 variants' }, { status: 400 });

  const scored = results.map(r => ({
    ...r,
    rate: metric === 'opens' ? r.opens / r.n : r.clicks / r.n,
  })).sort((a, b) => b.rate - a.rate);

  const [best, second] = scored;
  const significant    = isStatisticallySignificant(best, second, metric);

  if (significant) {
    await env.DB.prepare(`
      UPDATE ab_experiments SET status='concluded', winner_variant=? WHERE id=?
    `).bind(best.variant_id, experimentId).run();
  }

  return Response.json({ winner: best.variant_id, significant, stats: scored });
}

// Chi-square test for two proportions (p < 0.05)
function isStatisticallySignificant(a: AbStats & { rate: number }, b: AbStats & { rate: number }, metric: string): boolean {
  const aSucc = metric === 'opens' ? a.opens : a.clicks;
  const bSucc = metric === 'opens' ? b.opens : b.clicks;
  const aFail = a.n - aSucc;
  const bFail = b.n - bSucc;

  const total  = a.n + b.n;
  const totalS = aSucc + bSucc;
  const e11    = (a.n * totalS) / total;
  const e12    = (a.n * (total - totalS)) / total;
  const e21    = (b.n * totalS) / total;
  const e22    = (b.n * (total - totalS)) / total;

  if ([e11,e12,e21,e22].some(e => e < 5)) return false; // insufficient data

  const chi2 =
    ((aSucc - e11) ** 2 / e11) +
    ((aFail - e12) ** 2 / e12) +
    ((bSucc - e21) ** 2 / e21) +
    ((bFail - e22) ** 2 / e22);

  return chi2 > 3.841; // df=1, p<0.05
}

async function getVariants(env: Env, experimentId: string): Promise<AbVariant[]> {
  const { results } = await env.DB.prepare(`
    SELECT variant_id, subject, from_name, html_template, weight
    FROM ab_variants WHERE experiment_id=? ORDER BY variant_id
  `).bind(experimentId).all<AbVariant>();
  return results;
}

interface AbVariant {
  variant_id:    string;
  subject:       string;
  from_name:     string;
  html_template: string;
  weight:        number;
}

interface AbStats {
  variant_id: string;
  n:          number;
  opens:      number;
  clicks:     number;
}
```

## Implementation Details

- **Deterministic variant assignment** (hash on email) ensures a recipient always gets the same variant even if the send loop is retried, without storing the assignment before send.
- **Idempotency guard** (`SELECT 1 ... UNIQUE constraint`) prevents double-sends on retry.
- **Tracking pixel** uses a real 26-byte GIF with `Cache-Control: no-store` to defeat proxy caching.
- **Click wrapping** replaces all `href` links in the HTML template; the Worker records the click and issues a 302 redirect.
- **Chi-square test** with minimum expected cell size of 5 prevents declaring significance on tiny samples.
- Weights in `ab_variants` must sum to 1.0; validate this at experiment creation time.

## Anti-patterns

- Do not use `Math.random()` for variant assignment — it is non-deterministic and will assign different variants on retries.
- Do not declare a winner based solely on raw counts; always normalise to a rate and verify statistical significance.
- Do not wrap tracking URLs in a second tracking layer (double-redirect) — it degrades user experience and increases link rot risk.
- Do not store HTML templates as BLOBs in D1 beyond a few KB; for large templates, reference R2 objects instead.

## Gotchas

- Email clients prefetch images, inflating open rates. Use open rate only for directional insight; weight click rate more heavily.
- The chi-square test assumes independent observations. Recipients who forward the email can cause multiple opens/clicks for one send row — `IS NOT NULL` checks prevent double-counting in the DB.
- `btoa`/`atob` in Workers are available globally but encode to ASCII-safe base64 only; avoid characters outside the ASCII range in tracking IDs.
- D1 `UNIQUE (experiment_id, recipient_email)` will `ABORT` the insert if duplicate; wrap in try/catch in high-throughput loops.

## Verification

```bash
# 1. Create experiment and variants in D1
npx wrangler d1 execute ab-db --command "
  INSERT INTO ab_experiments (id, name) VALUES ('exp-001', 'Q3 Onboarding');
  INSERT INTO ab_variants VALUES ('exp-001','A','Welcome!','Orchords','<html>{{TRACKING_PIXEL}}</html>',0.5);
  INSERT INTO ab_variants VALUES ('exp-001','B','Get started now','Team Orchords','<html>{{TRACKING_PIXEL}}</html>',0.5);
"

# 2. Send to a small list
curl -X POST https://<worker>.workers.dev/ab/send \
  -H 'Content-Type: application/json' \
  -d '{"experimentId":"exp-001","recipients":["a@example.com","b@example.com"]}'

# 3. View stats
curl "https://<worker>.workers.dev/ab/stats?exp=exp-001"

# 4. Determine winner
curl -X POST https://<worker>.workers.dev/ab/winner \
  -H 'Content-Type: application/json' \
  -d '{"experimentId":"exp-001","metric":"clicks"}'
```

## Related

- `documentation/docs/policies/email/workers-email-open-tracking-pixel.md`
- `documentation/docs/policies/email/workers-transactional-email-queue.md`
- `documentation/docs/policies/email/workers-email-template-engine-r2.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://api.mailchannels.net/tx/v1/documentation
- https://en.wikipedia.org/wiki/Pearson%27s_chi-squared_test
