# Cookie Consent Banner with Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your web application uses analytics and marketing cookies that require prior consent under ePrivacy Directive / GDPR. You need to:

1. Inject a consent banner into every HTML page response without modifying your origin server.
2. Store the visitor's consent choice (accept / reject / granular) server-side in KV, keyed by a fingerprint that survives cross-session.
3. Block analytics `<script>` tags on subsequent requests until consent is given.
4. Track the consent version so that when your cookie policy changes, visitors are re-prompted.
5. Expose an opt-out API endpoint that downstream SDKs can call.

## Context

Cloudflare's **HTMLRewriter** API lets you transform HTML responses on-the-fly at the edge — adding, replacing, or removing elements — without buffering the full body. This makes it ideal for injecting a consent banner into pages served from any origin.

**KV** stores consent decisions globally with low read latency. Keys are scoped to a fingerprint derived from a first-party cookie set by the Worker (not the client IP, which changes).

Analytics tags (Google Analytics, Segment, Mixpanel, etc.) are injected as `<script>` tags in the `<head>`. The Worker rewrites those tags to inert `<template>` elements unless consent is confirmed.

## Solution

```typescript
// consent-banner.ts
export interface Env {
  CONSENT_KV: KVNamespace;
  CONSENT_POLICY_VERSION: string; // e.g. '2026-08'
  ANALYTICS_ALLOWED_ORIGINS: string; // comma-separated hostnames for script blocking
}

const CONSENT_COOKIE = '__consent_id';
const CONSENT_TTL = 60 * 60 * 24 * 365; // 1 year in seconds

interface ConsentRecord {
  consentId: string;
  version: string;
  analytics: boolean;
  marketing: boolean;
  functional: boolean;
  decidedAt: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // ── Opt-out API ──────────────────────────────────────────────────────────
    if (url.pathname === '/api/consent' && request.method === 'POST') {
      return handleConsentUpdate(request, env);
    }
    if (url.pathname === '/api/consent' && request.method === 'DELETE') {
      return handleConsentWithdrawal(request, env);
    }
    if (url.pathname === '/api/consent' && request.method === 'GET') {
      return handleConsentRead(request, env);
    }

    // ── Pass non-HTML requests through ──────────────────────────────────────
    const acceptHeader = request.headers.get('Accept') ?? '';
    if (!acceptHeader.includes('text/html')) {
      return fetch(request);
    }

    // ── Fetch origin response ────────────────────────────────────────────────
    const originResponse = await fetch(request);
    const contentType = originResponse.headers.get('Content-Type') ?? '';
    if (!contentType.includes('text/html')) {
      return originResponse;
    }

    // ── Resolve consent state ────────────────────────────────────────────────
    const { consentId, isNew } = resolveConsentId(request);
    const consentRecord = await env.CONSENT_KV.get<ConsentRecord>(
      `consent:${consentId}`,
      'json'
    );

    const hasValidConsent =
      consentRecord !== null &&
      consentRecord.version === env.CONSENT_POLICY_VERSION;

    // ── Transform HTML ───────────────────────────────────────────────────────
    const transformed = new HTMLRewriter()
      // Inject banner if no valid consent
      .on('body', new BannerInjector(hasValidConsent, env.CONSENT_POLICY_VERSION))
      // Block analytics scripts if no analytics consent
      .on('script[src]', new ScriptBlocker(consentRecord?.analytics === true))
      .transform(originResponse);

    // Set first-party consent ID cookie on new visitors
    const response = new Response(transformed.body, transformed);
    if (isNew) {
      response.headers.append(
        'Set-Cookie',
        `${CONSENT_COOKIE}=${consentId}; Max-Age=${CONSENT_TTL}; Path=/; SameSite=Lax; Secure; HttpOnly`
      );
    }
    return response;
  },
};

// ── HTMLRewriter handlers ─────────────────────────────────────────────────────

class BannerInjector implements HTMLRewriterElementContentHandlers {
  constructor(
    private hasConsent: boolean,
    private policyVersion: string
  ) {}

  element(element: Element): void {
    if (this.hasConsent) return;
    element.prepend(
      `<div id="consent-banner" data-policy-version="${this.policyVersion}" role="dialog" aria-label="Cookie consent">
  <p>We use cookies for analytics and personalisation. See our <a >Privacy Policy</a>.</p>
  <div class="consent-actions">
    <button onclick="window.__consent('accept-all')">Accept all</button>
    <button onclick="window.__consent('reject-all')">Reject all</button>
    <button onclick="window.__consent('manage')">Manage preferences</button>
  </div>
</div>
<script>
(function(){
  window.__consent = function(choice) {
    fetch('/api/consent', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({choice: choice, version: '${this.policyVersion}'})
    }).then(function(r){ if(r.ok) location.reload(); });
  };
})();
</script>`,
      { html: true }
    );
  }
}

class ScriptBlocker implements HTMLRewriterElementContentHandlers {
  private analyticsHosts = [
    'www.google-analytics.com',
    'ssl.google-analytics.com',
    'cdn.segment.com',
    'cdn.mixpanel.com',
    'js.hs-scripts.com',
  ];

  constructor(private analyticsAllowed: boolean) {}

  element(element: Element): void {
    if (this.analyticsAllowed) return;
    const src = element.getAttribute('src') ?? '';
    try {
      const host = new URL(src).hostname;
      if (this.analyticsHosts.some((h) => host.endsWith(h))) {
        // Replace with inert template to neutralise the script
        element.replace(
          `<!-- analytics blocked: consent not given (src=${src}) -->`,
          { html: true }
        );
      }
    } catch {
      // Relative URL or unparseable — leave as-is
    }
  }
}

// ── Consent API handlers ──────────────────────────────────────────────────────

async function handleConsentUpdate(request: Request, env: Env): Promise<Response> {
  const { choice, version, analytics, marketing, functional } =
    await request.json<{
      choice?: 'accept-all' | 'reject-all' | 'manage';
      version: string;
      analytics?: boolean;
      marketing?: boolean;
      functional?: boolean;
    }>();

  const consentId = extractConsentId(request);
  if (!consentId) return new Response('No consent ID', { status: 400 });

  let record: ConsentRecord;
  if (choice === 'accept-all') {
    record = { consentId, version, analytics: true, marketing: true, functional: true, decidedAt: new Date().toISOString() };
  } else if (choice === 'reject-all') {
    record = { consentId, version, analytics: false, marketing: false, functional: false, decidedAt: new Date().toISOString() };
  } else {
    // Granular — use explicit flags
    record = {
      consentId,
      version,
      analytics: analytics ?? false,
      marketing: marketing ?? false,
      functional: functional ?? true, // functional cookies typically always on
      decidedAt: new Date().toISOString(),
    };
  }

  await env.CONSENT_KV.put(`consent:${consentId}`, JSON.stringify(record), {
    expirationTtl: CONSENT_TTL,
  });

  return new Response(JSON.stringify({ ok: true, record }), {
    headers: { 'Content-Type': 'application/json' },
  });
}

async function handleConsentWithdrawal(request: Request, env: Env): Promise<Response> {
  const consentId = extractConsentId(request);
  if (!consentId) return new Response('No consent ID', { status: 400 });
  await env.CONSENT_KV.delete(`consent:${consentId}`);
  return new Response(JSON.stringify({ ok: true, withdrawn: true }), {
    headers: { 'Content-Type': 'application/json' },
  });
}

async function handleConsentRead(request: Request, env: Env): Promise<Response> {
  const consentId = extractConsentId(request);
  if (!consentId) return Response.json({ consented: false });
  const record = await env.CONSENT_KV.get<ConsentRecord>(`consent:${consentId}`, 'json');
  return Response.json({ consented: record !== null, record });
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function resolveConsentId(request: Request): { consentId: string; isNew: boolean } {
  const existing = extractConsentId(request);
  if (existing) return { consentId: existing, isNew: false };
  return { consentId: crypto.randomUUID(), isNew: true };
}

function extractConsentId(request: Request): string | null {
  const cookieHeader = request.headers.get('Cookie') ?? '';
  const match = cookieHeader.match(new RegExp(`${CONSENT_COOKIE}=([^;]+)`));
  return match ? match[1] : null;
}
```

## Implementation Details

**wrangler.toml:**

```toml
[[kv_namespaces]]
binding = "CONSENT_KV"
id = "<your-kv-namespace-id>"

[vars]
CONSENT_POLICY_VERSION = "2026-08"
```

**Version-based re-prompting.** When the cookie policy changes, update `CONSENT_POLICY_VERSION` (e.g., `"2026-08"` → `"2026-10"`). The `hasValidConsent` check compares the stored version against the current version; old records are considered invalid and the banner re-appears.

**Fingerprint approach.** The consent ID is stored in a first-party, `HttpOnly`, `Secure` cookie — not derived from the IP address or user agent (which would be PII processing without consent). The ID is opaque and contains no user-identifying information.

**CORS for single-page apps.** If your SPA calls `/api/consent` from a different subdomain, add a CORS middleware before the consent routes.

## Anti-patterns

- **Injecting the banner client-side only.** A slow JS load or an ad-blocker can prevent the banner from appearing at all, resulting in analytics firing without consent.
- **Storing consent decisions in `localStorage`.** LocalStorage is not accessible to the Worker and cannot be read on the first request. It also does not survive private browsing.
- **Using IP address as the consent fingerprint.** IP addresses are PII under GDPR. Using them as identifiers requires legal basis independent of the consent you are trying to capture.
- **Not versioning the consent record.** Without a version field, you cannot reliably re-prompt users when the policy changes — you would have to delete all KV records.
- **Blocking all `<script>` tags.** Only block known analytics/tracking hostnames. Blocking inline scripts or functional scripts will break the application.

## Gotchas

- `HTMLRewriter` processes the document in a streaming fashion. Handlers are called in document order. The `body` handler fires once per `<body>` tag open; use `element.prepend()` to inject content at the top of the body.
- `element.replace()` in `HTMLRewriter` replaces the entire element including tags. If you only want to neutralise the `src` attribute, use `element.removeAttribute('src')` instead.
- KV reads (`CONSENT_KV.get`) during the request path add latency. If banner injection is latency-sensitive, consider a short-lived `Cache-Control` for the KV read or use a request-level cache.
- `Set-Cookie` headers must be appended via `response.headers.append()`, not `.set()`, to avoid overwriting other cookies the origin set.
- The `CONSENT_POLICY_VERSION` var should be bumped in the Cloudflare dashboard or wrangler.toml and deployed — changing it in the Worker code alone triggers a redeploy, which is what you want.

## Verification

```bash
# 1. Fetch a page as a new visitor (no consent cookie)
curl -I https://your-site.example.com/
# → Look for Set-Cookie: __consent_id=...
# → Response body should contain <div id="consent-banner">

# 2. Accept consent
curl -X POST https://your-site.example.com/api/consent \
  -H 'Cookie: __consent_id=<id-from-step-1>' \
  -H 'Content-Type: application/json' \
  -d '{"choice": "accept-all", "version": "2026-08"}'
# → {"ok": true}

# 3. Fetch page again with cookie — banner should be absent
curl https://your-site.example.com/ \
  -H 'Cookie: __consent_id=<id-from-step-1>' | grep consent-banner
# → (no output)

# 4. Read consent record
curl https://your-site.example.com/api/consent \
  -H 'Cookie: __consent_id=<id-from-step-1>'
# → {"consented": true, "record": {"analytics": true, ...}}

# 5. Test version bump: update CONSENT_POLICY_VERSION to '2026-09' in wrangler.toml, redeploy
# → banner reappears for existing cookie holders
```

## Related

- `documentation/docs/policies/compliance/workers-pii-detection-scrubber.md`
- `documentation/docs/policies/compliance/workers-gdpr-data-deletion-pipeline.md`
- Cloudflare HTMLRewriter API
- ePrivacy Directive — Article 5(3)

## Sources

- Cloudflare HTMLRewriter: https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- Cloudflare KV: https://developers.cloudflare.com/kv/
- ePrivacy Directive 2002/58/EC Article 5(3): https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A02002L0058-20091219
- GDPR Recital 32 — Consent: https://gdpr-info.eu/recitals/no-32/
- IAB TCF v2.2 specification: https://iabeurope.eu/tcf-2-2/
