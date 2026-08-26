# CCPA Global Privacy Control (GPC) Opt-Out in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

California consumers can signal a "Do Not Sell or Share My Personal Information" preference by sending the `Sec-GPC: 1` HTTP header via a GPC-enabled browser. Your Worker must detect this signal on every request, persist the opt-out in D1, strip analytics beacons from HTML responses for opted-out users, and provide a signed opt-out confirmation API endpoint — all within the 24-month retention window required by CCPA.

---

## Context

California's CCPA (amended by CPRA) recognises the GPC signal as a legally valid opt-out of the sale or sharing of personal information as of January 2023. Workers are uniquely positioned to intercept the `Sec-GPC` header at the network edge before any analytics script fires. `HTMLRewriter` can surgically remove beacon `<script>` and `<img>` tags from the streamed HTML response without buffering the entire page. A signed confirmation token (HMAC-SHA-256) gives the consumer a verifiable receipt without exposing the raw opt-out record.

---

## Section 1 — D1 Schema

```sql
CREATE TABLE IF NOT EXISTS consumer_preferences (
  consumer_id     TEXT PRIMARY KEY,   -- hashed user ID or cookie value
  opted_out_at    INTEGER NOT NULL,   -- Unix epoch ms
  opt_out_source  TEXT NOT NULL,      -- 'gpc' | 'explicit_api' | 'consent_banner'
  expires_at      INTEGER NOT NULL,   -- opted_out_at + 24 months
  confirmation_token TEXT            -- HMAC-signed token returned to consumer
);

CREATE INDEX IF NOT EXISTS idx_cp_expires ON consumer_preferences(expires_at);

-- Opt-out confirmation log (immutable)
CREATE TABLE IF NOT EXISTS opt_out_log (
  id            TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  consumer_id   TEXT NOT NULL,
  event         TEXT NOT NULL,   -- 'opt_out' | 'opt_in' | 'expired'
  source        TEXT NOT NULL,
  ip            TEXT,
  gpc_present   INTEGER NOT NULL DEFAULT 0,
  ts            INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ool_consumer ON opt_out_log(consumer_id, ts);
```

---

## Section 2 — Worker Implementation

```typescript
interface Env {
  DB: D1Database;
  OPT_OUT_SECRET: string; // Workers Secret for HMAC signing
}

const TWENTY_FOUR_MONTHS_MS = 24 * 30 * 24 * 60 * 60 * 1000;

// ---------------------------------------------------------------------------
// HMAC signing
// ---------------------------------------------------------------------------
async function signToken(payload: string, secret: string): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    'raw',
    enc.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', key, enc.encode(payload));
  return btoa(String.fromCharCode(...new Uint8Array(sig)));
}

async function buildConfirmationToken(
  consumerId: string,
  ts: number,
  secret: string
): Promise<string> {
  const payload = `${consumerId}:${ts}`;
  const sig = await signToken(payload, secret);
  return btoa(JSON.stringify({ consumerId, ts, sig }));
}

// ---------------------------------------------------------------------------
// Identify consumer — prefer authenticated user ID, fall back to cookie
// ---------------------------------------------------------------------------
function resolveConsumerId(request: Request): string {
  const cookie = request.headers.get('Cookie') ?? '';
  const match  = cookie.match(/cid=([^;]+)/);
  return match ? match[1] : 'anonymous';
}

// ---------------------------------------------------------------------------
// Persist opt-out
// ---------------------------------------------------------------------------
async function persistOptOut(
  env: Env,
  consumerId: string,
  source: 'gpc' | 'explicit_api',
  ip: string | null
): Promise<string> {
  const now       = Date.now();
  const expiresAt = now + TWENTY_FOUR_MONTHS_MS;
  const token     = await buildConfirmationToken(consumerId, now, env.OPT_OUT_SECRET);

  await env.DB
    .prepare(
      `INSERT INTO consumer_preferences
         (consumer_id, opted_out_at, opt_out_source, expires_at, confirmation_token)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT(consumer_id) DO UPDATE SET
         opted_out_at   = excluded.opted_out_at,
         opt_out_source = excluded.opt_out_source,
         expires_at     = excluded.expires_at,
         confirmation_token = excluded.confirmation_token`
    )
    .bind(consumerId, now, source, expiresAt, token)
    .run();

  await env.DB
    .prepare(
      `INSERT INTO opt_out_log (consumer_id, event, source, ip, gpc_present, ts)
       VALUES (?, 'opt_out', ?, ?, ?, ?)`
    )
    .bind(consumerId, source, ip, source === 'gpc' ? 1 : 0, now)
    .run();

  return token;
}

// ---------------------------------------------------------------------------
// Check if consumer is opted out
// ---------------------------------------------------------------------------
async function isOptedOut(env: Env, consumerId: string): Promise<boolean> {
  const row = await env.DB
    .prepare(
      `SELECT 1 FROM consumer_preferences
       WHERE consumer_id = ? AND expires_at > ?`
    )
    .bind(consumerId, Date.now())
    .first();
  return row !== null;
}

// ---------------------------------------------------------------------------
// Main handler
// ---------------------------------------------------------------------------
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url        = new URL(request.url);
    const consumerId = resolveConsumerId(request);
    const gpc        = request.headers.get('Sec-GPC') === '1';
    const ip         = request.headers.get('CF-Connecting-IP');

    // Auto-persist GPC opt-out on every request that carries the signal
    if (gpc) {
      await persistOptOut(env, consumerId, 'gpc', ip);
    }

    // Explicit opt-out API
    if (request.method === 'POST' && url.pathname === '/v1/privacy/opt-out') {
      const token = await persistOptOut(env, consumerId, 'explicit_api', ip);
      return Response.json({
        status: 'opted_out',
        confirmation_token: token,
        expires_iso: new Date(Date.now() + TWENTY_FOUR_MONTHS_MS).toISOString(),
      });
    }

    // Opt-out status
    if (request.method === 'GET' && url.pathname === '/v1/privacy/opt-out') {
      const opted = await isOptedOut(env, consumerId);
      return Response.json({ opted_out: opted });
    }

    // Proxy the upstream response, stripping beacons for opted-out users
    const upstreamUrl = `https://origin.example.com${url.pathname}${url.search}`;
    const upstream    = await fetch(upstreamUrl, { headers: request.headers });
    const contentType = upstream.headers.get('Content-Type') ?? '';

    if (!contentType.includes('text/html')) return upstream;

    const optedOut = gpc || (await isOptedOut(env, consumerId));
    if (!optedOut) return upstream;

    // Strip analytics beacons from HTML via HTMLRewriter
    return new HTMLRewriter()
      .on('script[src*="analytics"], script[src*="gtag"], script[src*="segment"]', {
        element(el) { el.remove(); },
      })
      .on('img[src*="beacon"], img[src*="pixel"], noscript', {
        element(el) { el.remove(); },
      })
      .on('head', {
        element(el) {
          el.append(
            '<meta name="gpc-opt-out" content="true">',
            { html: true }
          );
        },
      })
      .transform(upstream);
  },
} satisfies ExportedHandler<Env>;
```

---

## Section 3 — Testing / Verification

```bash
# Simulate GPC signal
curl -s https://api.example.com/ \
  -H "Sec-GPC: 1" \
  -H "Cookie: cid=test-consumer-123" \
  -D - | grep -E "(gpc-opt-out|analytics)"

# Call explicit opt-out endpoint
curl -X POST https://api.example.com/v1/privacy/opt-out \
  -H "Cookie: cid=test-consumer-123"
# Expected: {"status":"opted_out","confirmation_token":"...","expires_iso":"..."}

# Verify opt-out persisted in D1
npx wrangler d1 execute MY_DB \
  --command "SELECT consumer_id, opt_out_source, datetime(opted_out_at/1000,'unixepoch') AS when_ FROM consumer_preferences"

# Check status endpoint
curl https://api.example.com/v1/privacy/opt-out \
  -H "Cookie: cid=test-consumer-123"
# Expected: {"opted_out":true}
```

---

## Anti-patterns

- **Ignoring GPC on sub-requests** — Analytics libraries often fire beacons from within iframes or workers; ensure every sub-request path checks the opt-out status.
- **Storing GPC preference only in a cookie** — Cookies can be cleared; D1 persistence ensures the opt-out survives browser resets.
- **Blocking ALL third-party resources for opted-out users** — Only remove scripts and pixels involved in selling/sharing data; blocking unrelated CDN assets breaks the page.
- **Not renewing the 24-month window on re-assertion** — CCPA requires honouring the opt-out; the `ON CONFLICT … DO UPDATE` pattern refreshes the expiry on every GPC signal.

---

## Gotchas

- `Sec-GPC: 1` is set by Firefox, Brave, and DuckDuckGo browsers by default; it will be present on a meaningful fraction of California traffic.
- `HTMLRewriter` streams the response; selectors run on each element as it passes through — avoid stateful side-effects inside element handlers.
- The confirmation token is a base64-encoded JSON envelope containing an HMAC signature; verify it server-side before trusting any consumer-presented token.
- D1 `ON CONFLICT DO UPDATE` requires the conflicting column to be declared as `PRIMARY KEY` or have a `UNIQUE` constraint.
- Opt-out records themselves contain a `consumer_id` which may be personal data; include them in your GDPR erasure flow if you operate in the EU as well.

---

## Verification

```bash
# Confirm opt-out log is append-only
npx wrangler d1 execute MY_DB \
  --command "SELECT event, source, gpc_present, ts FROM opt_out_log ORDER BY ts DESC LIMIT 10"

# Confirm expired records are excluded from isOptedOut check
npx wrangler d1 execute MY_DB \
  --command "SELECT consumer_id, expires_at < unixepoch('now')*1000 AS expired FROM consumer_preferences"

# Run unit tests
npx vitest run src/ccpa.test.ts
```

---

## Related

- `workers-gdpr-right-to-erasure-d1.md`
- `workers-gdpr-data-portability-r2.md`

---

## Sources

- California Consumer Privacy Act (CCPA/CPRA) — https://oag.ca.gov/privacy/ccpa
- Global Privacy Control Specification — https://globalprivacycontrol.org/
- Cloudflare HTMLRewriter — https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
