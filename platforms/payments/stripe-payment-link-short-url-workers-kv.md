# Stripe Payment Link Short URLs with Cloudflare Workers and KV

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Stripe payment links have URLs in the form `https://buy.stripe.com/live_aBcDeFgH1234`. Sharing these directly in SMS, email footers, or QR codes is functional but brittle: changing the underlying product or price requires creating a new payment link and updating every place the URL was used. You want short, memorable URLs (`pay.example.com/pro`) that redirect to the current Stripe payment link — switchable without touching the distribution channel — with click analytics stored in KV and optional UTM-passthrough to Stripe.

## Context

Cloudflare Workers with KV is the natural fit: KV read latency at the edge is <5 ms globally, the redirect logic is a single `Response.redirect()`, and KV's eventual-consistency model (60-second lag on propagation) is perfectly acceptable for payment link routing where updates are deliberate admin actions, not real-time data. Store the slug-to-URL mapping in KV, optionally mirrored in D1 for audit history, and expose a protected admin API to manage slugs. A cron Trigger handles stale-link detection by polling the Stripe API.

---

## 1. KV Namespace and Data Model

```bash
# wrangler.toml
[[kv_namespaces]]
binding = "PAYMENT_LINKS"
id = "your-namespace-id"

# Key pattern:  slug:<slug>
# Value:        JSON LinkRecord
```

```typescript
// src/types.ts
export interface LinkRecord {
  stripeUrl: string;           // full buy.stripe.com URL
  stripePaymentLinkId: string; // pl_xxx for Stripe API lookups
  label: string;               // human-readable: "Pro Plan Monthly"
  active: boolean;
  utmSource?: string;          // appended as ?utm_source=...
  createdAt: number;
  updatedAt: number;
}

export interface Env {
  PAYMENT_LINKS: KVNamespace;
  DB: D1Database;
  STRIPE_SECRET_KEY: string;
  ADMIN_TOKEN: string;
}
```

## 2. Redirect Worker (Hot Path)

```typescript
// src/redirect.ts
import { Env, LinkRecord } from './types';

export async function handleRedirect(
  req: Request,
  env: Env,
  slug: string
): Promise<Response> {
  const record = await env.PAYMENT_LINKS.get<LinkRecord>(
    `slug:${slug}`,
    { type: 'json' }
  );

  if (!record || !record.active) {
    return new Response('Payment link not found.', { status: 404 });
  }

  // Passthrough UTM params from inbound URL
  const inbound = new URL(req.url);
  const dest = new URL(record.stripeUrl);

  const utmParams = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content'];
  for (const param of utmParams) {
    const val = inbound.searchParams.get(param);
    if (val) dest.searchParams.set(param, val);
    else if (param === 'utm_source' && record.utmSource) {
      dest.searchParams.set('utm_source', record.utmSource);
    }
  }

  // Non-blocking click counter (fire-and-forget)
  void recordClick(env, slug, req);

  return Response.redirect(dest.toString(), 302);
}

async function recordClick(env: Env, slug: string, req: Request): Promise<void> {
  const key = `clicks:${slug}:${dayBucket()}`;
  const raw = await env.PAYMENT_LINKS.get(key);
  const count = parseInt(raw ?? '0', 10) + 1;
  // TTL of 90 days keeps KV tidy
  await env.PAYMENT_LINKS.put(key, String(count), { expirationTtl: 90 * 86400 });
}

function dayBucket(): string {
  return new Date().toISOString().slice(0, 10); // 'YYYY-MM-DD'
}
```

## 3. Admin API: CRUD for Slugs

```typescript
// src/admin.ts
import Stripe from 'stripe';
import { Env, LinkRecord } from './types';

function requireAuth(req: Request, env: Env): boolean {
  return req.headers.get('Authorization') === `Bearer ${env.ADMIN_TOKEN}`;
}

export async function handleAdmin(req: Request, env: Env, slug: string): Promise<Response> {
  if (!requireAuth(req, env)) {
    return new Response('Unauthorized', { status: 401 });
  }

  if (req.method === 'PUT') {
    const body: Partial<LinkRecord> & { stripePaymentLinkId: string } = await req.json();
    const stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2024-06-20' });

    // Verify the Stripe payment link exists and is active
    const pl = await stripe.paymentLinks.retrieve(body.stripePaymentLinkId);
    if (!pl.active) {
      return Response.json({ error: 'Stripe payment link is not active.' }, { status: 400 });
    }

    const now = Math.floor(Date.now() / 1000);
    const existing = await env.PAYMENT_LINKS.get<LinkRecord>(`slug:${slug}`, { type: 'json' });

    const record: LinkRecord = {
      stripeUrl: pl.url,
      stripePaymentLinkId: pl.id,
      label: body.label ?? pl.id,
      active: body.active ?? true,
      utmSource: body.utmSource,
      createdAt: existing?.createdAt ?? now,
      updatedAt: now,
    };

    await env.PAYMENT_LINKS.put(`slug:${slug}`, JSON.stringify(record));

    // Mirror to D1 audit log
    await env.DB.prepare(
      `INSERT INTO payment_link_history (slug, stripe_payment_link_id, stripe_url, label, changed_at)
       VALUES (?, ?, ?, ?, ?)`
    ).bind(slug, pl.id, pl.url, record.label, now).run();

    return Response.json({ slug, record });
  }

  if (req.method === 'DELETE') {
    const existing = await env.PAYMENT_LINKS.get<LinkRecord>(`slug:${slug}`, { type: 'json' });
    if (!existing) return new Response('Not found', { status: 404 });
    existing.active = false;
    await env.PAYMENT_LINKS.put(`slug:${slug}`, JSON.stringify(existing));
    return Response.json({ slug, active: false });
  }

  if (req.method === 'GET') {
    // Return click counts for last 30 days
    const clicks: Record<string, number> = {};
    for (let d = 0; d < 30; d++) {
      const date = new Date(Date.now() - d * 86400_000).toISOString().slice(0, 10);
      const raw = await env.PAYMENT_LINKS.get(`clicks:${slug}:${date}`);
      if (raw) clicks[date] = parseInt(raw, 10);
    }
    const record = await env.PAYMENT_LINKS.get<LinkRecord>(`slug:${slug}`, { type: 'json' });
    return Response.json({ record, clicks });
  }

  return new Response('Method Not Allowed', { status: 405 });
}
```

## 4. D1 Audit Schema

```sql
-- migrations/0012_payment_link_history.sql
CREATE TABLE IF NOT EXISTS payment_link_history (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  slug                   TEXT NOT NULL,
  stripe_payment_link_id TEXT NOT NULL,
  stripe_url             TEXT NOT NULL,
  label                  TEXT,
  changed_at             INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_link_history_slug ON payment_link_history (slug, changed_at DESC);
```

## 5. Cron Trigger: Detect Deactivated Stripe Links

```typescript
// src/index.ts — scheduled handler
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2024-06-20' });
    // List all KV keys (slug:*) in batches
    let cursor: string | undefined;
    do {
      const list = await env.PAYMENT_LINKS.list({ prefix: 'slug:', cursor, limit: 100 });
      cursor = list.list_complete ? undefined : list.cursor;

      for (const key of list.keys) {
        const record = await env.PAYMENT_LINKS.get<LinkRecord>(key.name, { type: 'json' });
        if (!record || !record.active) continue;

        const pl = await stripe.paymentLinks.retrieve(record.stripePaymentLinkId)
          .catch(() => null);

        if (!pl || !pl.active) {
          record.active = false;
          await env.PAYMENT_LINKS.put(key.name, JSON.stringify(record));
          console.log(`Deactivated stale slug ${key.name.replace('slug:', '')} → ${record.stripePaymentLinkId}`);
        }
      }
    } while (cursor);
  },
};
```

---

## Anti-patterns

- **Storing the raw Stripe URL in your own database and never revalidating** — Stripe can change the domain or the link can be archived. Always poll `stripe.paymentLinks.retrieve` to verify liveness.
- **Using permanent (301) redirects** — browsers cache 301s aggressively; you lose the ability to swap the destination URL. Always use 302 (or 307 for POST passthrough).
- **Blocking the redirect on the click counter write** — this adds 10–30 ms. Use `void recordClick(...)` to fire-and-forget; the hit may be lost on Worker crash, which is acceptable for analytics.
- **Putting UTM parameters in the KV record and hardcoding them** — allow per-request UTM passthrough so a single slug can carry different campaign tags from different emails.

## Gotchas

- KV's eventual consistency means a newly created slug may not be visible globally for up to 60 seconds. On slug creation, return the full Stripe URL as a fallback in the admin response.
- `stripe.paymentLinks.retrieve` returns the same URL regardless of price changes made after link creation. To surface price changes, list `line_items` via `stripe.paymentLinks.listLineItems`.
- Payment links created in test mode have URLs starting `https://buy.stripe.com/test_…`. The Worker must handle both environments if you share the same KV namespace.
- KV `list()` with `prefix` iterates metadata only; values require separate `get()` calls. For large slug counts (>1 000), batch `stripe.paymentLinks.list()` instead of re-fetching every slug individually in the cron handler.

## Verification

```bash
# Create a slug
curl -X PUT https://pay.example.com/admin/pro \
  -H 'Authorization: Bearer your-admin-token' \
  -H 'Content-Type: application/json' \
  -d '{"stripePaymentLinkId":"pl_xxx","label":"Pro Plan"}'

# Test redirect
curl -I https://pay.example.com/pro
# Expect: HTTP/2 302, Location: https://buy.stripe.com/live_...

# Check click stats
curl https://pay.example.com/admin/pro \
  -H 'Authorization: Bearer your-admin-token'
```

## Related

- `payment-link-generation.md`
- `payment-link-dynamic-pricing-workers-kv.md`
- `stripe-pricing-table-embed.md`
- `stripe-checkout-session-cloudflare-workers.md`
- `multi-currency-kv-exchange-rate-cache-edge-pricing.md`

## Sources

- https://docs.stripe.com/payment-links
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://docs.stripe.com/api/payment_links/object
