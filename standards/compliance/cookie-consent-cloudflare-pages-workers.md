# Cookie Consent — Cloudflare Pages Functions, Workers KV, IAB TCF v2.2 & GPC

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project's web client sets third-party analytics cookies and loads embeds that set additional
cookies. Without a compliant cookie consent mechanism, EU/EEA users are being tracked
without valid consent (GDPR Art. 6 + ePrivacy Directive). The team needs an end-to-end
implementation using Cloudflare Pages Functions for the consent gate, KV for consent
persistence, and IAB TCF v2.2 for interoperability.

## Context

The ePrivacy Directive (transposed in each member state) requires informed, prior,
freely-given, specific consent before setting non-essential cookies. GDPR applies to any
personal data processed via those cookies.

IAB Europe's Transparency and Consent Framework (TCF) v2.2 (the current version as of
2026, post the EDPB's 2024 guidance) provides a standard `tcString` that encodes a
user's vendor-level choices. Cloudflare Pages Functions run on the edge and can inspect
and set headers before HTML reaches the browser.

Global Privacy Control (GPC) is a browser signal (HTTP header `Sec-GPC: 1` or
`navigator.globalPrivacyControl === true`) that several EU/US jurisdictions (incl.
California, UK ICO guidance) treat as a valid opt-out signal.

## TCF v2.2 Key Concepts

```
+-------------------------------+------------------------------------------+
| Concept                       | Engineering note                         |
+-------------------------------+------------------------------------------+
| CMP ID                        | Register with IAB Europe; embed in tcString|
| Purpose 1                     | "Store / access info on device" = cookies|
| Legitimate Interest override  | Purposes 2-10 may use LI, not Purpose 1  |
| Vendor list                   | Global Vendor List (GVL) v3 JSON         |
| TC string                     | Base64url-encoded binary; set in         |
|                               | euconsent-v2 cookie                      |
| Post-message API              | __tcfapi() for in-page vendor checks     |
+-------------------------------+------------------------------------------+
```

## KV Consent Storage Schema

```
// Key: consent:{hashedFingerprint}
// Value: JSON blob
{
  "tcString":      "CPzHq4APzH...",   // IAB TCF v2.2 encoded string
  "gpc":           false,             // GPC signal at time of consent
  "purposes":      { "1": true, "3": false, "4": false, "7": true },
  "vendors":       { "755": true, "8": false },
  "consentVersion": 3,
  "consentedAt":   1724284800000,
  "expiresAt":     1755820800000      // 1 year from consent
}

// KV namespace: COOKIE_CONSENT
// KV TTL: 365 days (set via expirationTtl on put)
```

```typescript
// pages/functions/api/consent.ts  — Pages Function (runs at edge)
import type { EventContext } from '@cloudflare/workers-types';

interface Env {
  COOKIE_CONSENT: KVNamespace;
  CONSENT_SALT: string;
}

export async function onRequestPost(ctx: EventContext<Env, string, unknown>): Promise<Response> {
  const body = await ctx.request.json<{
    tcString: string;
    purposes: Record<string, boolean>;
    vendors: Record<string, boolean>;
    gpc?: boolean;
  }>();

  const fingerprint = await deriveFingerprint(ctx.request, ctx.env.CONSENT_SALT);
  const key = `consent:${fingerprint}`;

  const record = {
    tcString:      body.tcString,
    gpc:           body.gpc ?? false,
    purposes:      body.purposes,
    vendors:       body.vendors,
    consentVersion: 3,
    consentedAt:   Date.now(),
    expiresAt:     Date.now() + 365 * 24 * 3600 * 1000,
  };

  await ctx.env.COOKIE_CONSENT.put(key, JSON.stringify(record), {
    expirationTtl: 365 * 24 * 3600,
  });

  // Set the IAB TCF euconsent-v2 cookie via Set-Cookie header
  const response = Response.json({ ok: true, consentedAt: record.consentedAt });
  response.headers.set('Set-Cookie',
    `euconsent-v2=${body.tcString}; Path=/; Max-Age=${365*24*3600}; Secure; SameSite=Lax`
  );
  return response;
}

export async function onRequestGet(ctx: EventContext<Env, string, unknown>): Promise<Response> {
  const gpc = ctx.request.headers.get('Sec-GPC') === '1';
  if (gpc) {
    // GPC treated as opt-out for all non-essential purposes
    return Response.json({ gpc: true, purposes: {}, vendors: {} });
  }

  const fingerprint = await deriveFingerprint(ctx.request, ctx.env.CONSENT_SALT);
  const raw = await ctx.env.COOKIE_CONSENT.get(`consent:${fingerprint}`);
  if (!raw) return Response.json({ noConsent: true });

  const record = JSON.parse(raw);
  if (record.expiresAt < Date.now()) {
    // Expired — treat as no consent
    return Response.json({ expired: true, noConsent: true });
  }
  return Response.json(record);
}

async function deriveFingerprint(request: Request, salt: string): Promise<string> {
  const ip   = request.headers.get('CF-Connecting-IP') ?? '';
  const ua   = request.headers.get('User-Agent') ?? '';
  const data = `${ip}|${ua}|${salt}`;
  const buf  = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(data));
  return Array.from(new Uint8Array(buf).slice(0, 16))
    .map(b => b.toString(16).padStart(2,'0')).join('');
}
```

## Pages Function Consent Gate Middleware

```typescript
// pages/functions/_middleware.ts
export async function onRequest(ctx: EventContext<Env, string, unknown>): Promise<Response> {
  const url = new URL(ctx.request.url);

  // GPC: honour as opt-out before anything else
  if (ctx.request.headers.get('Sec-GPC') === '1') {
    // Strip analytics query params that could track user
    url.searchParams.delete('utm_source');
    url.searchParams.delete('utm_medium');
    url.searchParams.delete('fbclid');
    const clean = new Request(url.toString(), ctx.request);
    const response = await ctx.next(clean);
    response.headers.set('Permissions-Policy', 'interest-cohort=()');
    return response;
  }

  // Paths that must always load (consent UI itself, static assets)
  if (url.pathname.startsWith('/api/consent') ||
      url.pathname.startsWith('/consent') ||
      url.pathname.match(/\.(js|css|woff2|ico|png|svg)$/)) {
    return ctx.next();
  }

  // Check KV for stored consent
  const fingerprint = await deriveFingerprint(ctx.request, (ctx.env as Env).CONSENT_SALT);
  const raw = await (ctx.env as Env).COOKIE_CONSENT.get(`consent:${fingerprint}`);
  const hasConsent = raw !== null && JSON.parse(raw).expiresAt > Date.now();

  const response = await ctx.next();

  if (!hasConsent) {
    // Inject consent banner script tag via HTMLRewriter
    return new HTMLRewriter()
      .on('body', {
        element(el) {
          el.append('<script  defer></script>', { html: true });
        }
      })
      .transform(response);
  }

  return response;
}
```

## Mobile Consent Modal UX

```
[WebView or React Native WebView loads example.com]
        |
        v
  Pages Function middleware detects no KV consent record
        |
        v
  Injects consent-banner.js into <body>
        |
        v
  Banner renders full-screen modal:
  +--------------------------------------------------+
  | We use cookies                                    |
  |                                                  |
  | Essential (always on)                             |
  | [ ] Analytics — Helps us improve example project            |
  | [ ] Embeds  — Load external media (YouTube etc.) |
  |                                                  |
  | Your browser is sending GPC: [YES/NO]             |
  | (if YES, non-essential are pre-disabled)         |
  |                                                  |
  | [Accept selected]      [Reject all optional]     |
  | [Manage preferences]                             |
  +--------------------------------------------------+
        |
        v
  POST /api/consent { tcString, purposes, vendors, gpc }
        |
        v
  KV record written, euconsent-v2 cookie set
        |
        v
  Modal dismissed; page reloads without banner
```

## GPC Header Handling

```
+------------------------+---------------------------------------------+
| Signal                 | example project response                               |
+------------------------+---------------------------------------------+
| Sec-GPC: 1 (HTTP hdr) | Strip tracking params; no analytics cookies  |
| navigator.globalPrivacyControl | Same, detected client-side         |
| Neither                | Show consent modal on first visit           |
| euconsent-v2 cookie    | Read TC string; honour purpose/vendor flags |
+------------------------+---------------------------------------------+
```

GPC must be honoured under:
- California CPRA (opt-out of sale/sharing)
- UK ICO cookie guidance (2024)
- French CNIL TCF guidance
- German DSK position paper (2025)

## Anti-patterns

- Setting analytics cookies before consent modal is acknowledged.
- Storing `euconsent-v2` in `localStorage` only — must also be in a cookie for
  server-side consent verification.
- Using a pre-checked "I agree to analytics" checkbox — ePrivacy requires unchecked
  default for non-essential.
- Treating a scrolled-past banner as implied consent — EDPB is explicit this is invalid.
- Ignoring GPC signal and showing the full consent modal anyway — wastes UX goodwill and
  may be non-compliant in California.
- Using a fingerprint as a long-term user identifier beyond the consent TTL — consent
  fingerprints must be treated as temporary, not profiling keys.

## Gotchas

- **TCF v2.2 vs v3**: IAB is working on TCF v3; confirm your CMP is on the current
  version before each annual audit.
- **KV eventual consistency**: consent records written in one region may take up to 60 s
  to replicate globally; use `{ cacheTtl: 0 }` on reads during the consent window.
- **`euconsent-v2` cookie size**: TC strings with many vendors can exceed 4 KB — split
  into `euconsent-v2` (first chunk) and `euconsent-v2-1` etc. if needed.
- **Pages Functions vs Workers**: Pages Functions share KV bindings but not Durable
  Objects by default; ensure the `COOKIE_CONSENT` KV namespace is bound in
  `wrangler.toml` under `[[kv_namespaces]]` with `pages_dev = true`.
- **Cookie SameSite on mobile WebViews**: Android WebView may not send `SameSite=Lax`
  cookies on POST redirects; test explicitly on API 29+.

## Verification

```bash
# Check KV record exists for a test fingerprint
wrangler kv key get --namespace-id $COOKIE_CONSENT_KV_ID "consent:$(echo -n 'test' | sha256sum | cut -c1-32)"

# Confirm GPC header strips tracking params
curl -s -I -H "Sec-GPC: 1" "https://example.com/?utm_source=test" | grep -i location

# Validate euconsent-v2 cookie is set after POST /api/consent
curl -s -X POST https://example.com/api/consent \
  -H "Content-Type: application/json" \
  -d '{"tcString":"CPtest","purposes":{"1":true},"vendors":{}}' \
  -c /tmp/cookies.txt -v 2>&1 | grep -i "set-cookie"

# Verify consent banner is injected when no consent record exists
curl -s https://example.com/ | grep -c "consent-banner.js"
# Expected: 1
```

## Related

- `gdpr-cookie-consent-implementation.md`
- `gdpr-lawful-basis-workers-d1-consent.md`
- `cookie-consent-management-platform.md`
- `gdpr-consent-management.md`
- `ccpa-opt-out.md`

## Sources

- IAB Europe TCF v2.2 specification — iabeurope.eu
- EDPB Guidelines 05/2020 on consent
- ePrivacy Directive 2002/58/EC, Art. 5(3)
- French CNIL "Cookies" guidance (updated 2024)
- Global Privacy Control specification — globalprivacycontrol.org
- Cloudflare Pages Functions docs — developers.cloudflare.com/pages/functions
- Cloudflare KV docs — developers.cloudflare.com/kv
