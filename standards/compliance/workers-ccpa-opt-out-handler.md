# CCPA Opt-Out (Do Not Sell/Share) Handler in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your site serves California residents and must comply with CCPA/CPRA. Users exercise their "Do Not Sell or Share My Personal Information" right via an opt-out link or the Global Privacy Control (GPC) browser signal. You need to detect GPC, persist the opt-out decision for 12 months, suppress outbound data sharing to third-party pixels/analytics, inject required CCPA privacy policy links into every HTML page, and expose an `/api/ccpa/opt-out` endpoint — all at the edge without touching origin servers.

## Context

CCPA (California Consumer Privacy Act) and its 2023 CPRA amendments require:
- Honoring the GPC header (`Sec-GPC: 1`) as a valid opt-out signal as of 2023.
- Providing a "Do Not Sell or Share My Personal Information" link on every page.
- Processing opt-out requests within 15 business days.
- Maintaining opt-out for at least 12 months before re-asking consent.
- Suppressing data sales/sharing to third parties when opted out.

Cloudflare Workers sit in front of every request, making them ideal for: reading GPC headers, rewriting HTML to inject required links, removing or neutering third-party pixel tags, and persisting opt-out state in KV with a 12-month TTL.

## Solution

```typescript
import { HTMLRewriter } from '@cloudflare/workers-types';

export interface Env {
  CCPA_OPT_OUTS: KVNamespace;     // KV for opt-out persistence
  ORIGIN: string;                   // e.g. "https://origin.example.com"
  THIRD_PARTY_PIXEL_DOMAINS: string; // comma-separated, e.g. "pixel.facebook.com,analytics.tiktok.com"
}

const OPT_OUT_TTL_SECONDS = 60 * 60 * 24 * 365; // 12 months
const CCPA_COOKIE = 'ccpa_opt_out';
const KV_PREFIX = 'ccpa:opt_out:';

// ─── GPC detection ────────────────────────────────────────────────────────────

function detectGpc(request: Request): boolean {
  return request.headers.get('Sec-GPC') === '1';
}

function getCcpaCookie(request: Request): string | null {
  const cookie = request.headers.get('Cookie') ?? '';
  const match = cookie.match(new RegExp(`(?:^|;\\s*)${CCPA_COOKIE}=([^;]+)`));
  return match ? match[1] : null;
}

// ─── KV helpers ───────────────────────────────────────────────────────────────

async function isOptedOut(env: Env, userId: string): Promise<boolean> {
  const val = await env.CCPA_OPT_OUTS.get(`${KV_PREFIX}${userId}`);
  return val === 'true';
}

async function recordOptOut(
  env: Env,
  userId: string,
  source: 'gpc' | 'explicit' | 'api'
): Promise<void> {
  const record = JSON.stringify({
    optedOut: true,
    source,
    timestamp: new Date().toISOString(),
    expiresAt: new Date(Date.now() + OPT_OUT_TTL_SECONDS * 1000).toISOString(),
  });
  await env.CCPA_OPT_OUTS.put(
    `${KV_PREFIX}${userId}`,
    record,
    { expirationTtl: OPT_OUT_TTL_SECONDS }
  );
}

async function clearOptOut(env: Env, userId: string): Promise<void> {
  await env.CCPA_OPT_OUTS.delete(`${KV_PREFIX}${userId}`);
}

// ─── User identification (anonymous fingerprint or session token) ──────────────

function deriveUserId(request: Request): string {
  // In production, prefer a real authenticated user ID from a session cookie.
  // Fallback: hash of IP + User-Agent for anonymous visitors.
  const ip = request.headers.get('CF-Connecting-IP') ?? 'unknown';
  const ua = request.headers.get('User-Agent') ?? '';
  // Simple deterministic concat — replace with crypto.subtle.digest in prod
  return btoa(`${ip}|${ua}`).slice(0, 32);
}

// ─── Opt-out API endpoint ──────────────────────────────────────────────────────

async function handleOptOutApi(
  request: Request,
  env: Env
): Promise<Response> {
  const url = new URL(request.url);

  if (request.method === 'POST' && url.pathname === '/api/ccpa/opt-out') {
    const userId = deriveUserId(request);
    await recordOptOut(env, userId, 'explicit');

    const res = new Response(
      JSON.stringify({ success: true, message: 'Opt-out recorded for 12 months.' }),
      {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }
    );
    res.headers.append(
      'Set-Cookie',
      `${CCPA_COOKIE}=true; Max-Age=${OPT_OUT_TTL_SECONDS}; Path=/; SameSite=Lax; Secure`
    );
    return res;
  }

  if (request.method === 'DELETE' && url.pathname === '/api/ccpa/opt-out') {
    const userId = deriveUserId(request);
    await clearOptOut(env, userId);
    const res = new Response(
      JSON.stringify({ success: true, message: 'Opt-out cleared.' }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    );
    res.headers.append(
      'Set-Cookie',
      `${CCPA_COOKIE}=; Max-Age=0; Path=/; SameSite=Lax; Secure`
    );
    return res;
  }

  if (request.method === 'GET' && url.pathname === '/api/ccpa/status') {
    const userId = deriveUserId(request);
    const raw = await env.CCPA_OPT_OUTS.get(`${KV_PREFIX}${userId}`);
    return new Response(raw ?? JSON.stringify({ optedOut: false }), {
      headers: { 'Content-Type': 'application/json' },
    });
  }

  return new Response('Not found', { status: 404 });
}

// ─── HTMLRewriter: inject CCPA links and remove pixel scripts ─────────────────

class PixelScriptRemover implements HTMLRewriterElementContentHandlers {
  private blockedDomains: string[];
  constructor(blockedDomains: string[]) {
    this.blockedDomains = blockedDomains;
  }
  element(el: Element) {
    const src = el.getAttribute('src') ?? el.getAttribute('data-src') ?? '';
    const isPixel = this.blockedDomains.some((d) => src.includes(d));
    if (isPixel) {
      el.remove();
    }
  }
}

class CcpaLinkInjector implements HTMLRewriterElementContentHandlers {
  element(el: Element) {
    el.append(
      `<div id="ccpa-footer-link" style="font-size:12px;margin-top:8px">
  <a  rel="nofollow">Do Not Sell or Share My Personal Information</a>
  &nbsp;|&nbsp;
  <a >CCPA Privacy Notice</a>
</div>`,
      { html: true }
    );
  }
}

function rewriteForOptOut(
  response: Response,
  blockedDomains: string[],
  isOptedOut: boolean
): Response {
  const rewriter = new HTMLRewriter();

  // Always inject CCPA links into the footer
  rewriter.on('footer', new CcpaLinkInjector());

  // Remove third-party pixels when opted out
  if (isOptedOut) {
    rewriter
      .on('script[src]', new PixelScriptRemover(blockedDomains))
      .on('img[src]', new PixelScriptRemover(blockedDomains))
      .on('iframe[src]', new PixelScriptRemover(blockedDomains));
  }

  return rewriter.transform(response);
}

// ─── Main Worker entry point ───────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const blockedDomains = env.THIRD_PARTY_PIXEL_DOMAINS.split(',').map((d) => d.trim());

    // Handle CCPA API routes
    if (url.pathname.startsWith('/api/ccpa/')) {
      return handleOptOutApi(request, env);
    }

    // Determine opt-out status
    const gpc = detectGpc(request);
    const cookie = getCcpaCookie(request);
    const userId = deriveUserId(request);

    let optedOut = cookie === 'true' || gpc;
    if (!optedOut) {
      optedOut = await isOptedOut(env, userId);
    }

    // Auto-persist GPC signal on first encounter
    if (gpc && !(cookie === 'true')) {
      await recordOptOut(env, userId, 'gpc');
    }

    // Proxy to origin
    const originUrl = `${env.ORIGIN}${url.pathname}${url.search}`;
    const originReq = new Request(originUrl, {
      method: request.method,
      headers: request.headers,
      body: request.body,
    });
    const originRes = await fetch(originReq);

    const contentType = originRes.headers.get('Content-Type') ?? '';
    if (contentType.includes('text/html')) {
      const rewritten = rewriteForOptOut(originRes, blockedDomains, optedOut);
      if (gpc && cookie !== 'true') {
        rewritten.headers.append(
          'Set-Cookie',
          `${CCPA_COOKIE}=true; Max-Age=${OPT_OUT_TTL_SECONDS}; Path=/; SameSite=Lax; Secure`
        );
      }
      rewritten.headers.set('X-CCPA-Opt-Out', optedOut ? 'true' : 'false');
      return rewritten;
    }

    return originRes;
  },
};
```

## Implementation Details

**GPC auto-persistence**: When `Sec-GPC: 1` is detected on a request with no existing opt-out cookie, `recordOptOut` is called with source `'gpc'` and a 12-month KV TTL. Subsequent requests are served from the cookie without a KV read.

**Three-layer opt-out check**: Cookie → GPC header → KV. This order minimises KV reads (and cost) for returning visitors who already have the cookie set.

**HTMLRewriter streaming**: `PixelScriptRemover` operates on `<script src>`, `<img src>` (tracking pixels), and `<iframe src>` (embedded widgets). The rewriter streams — no buffering of full HTML in memory.

**Link injection target**: `<footer>` is used as the injection anchor. If your site uses a different element (e.g., `#site-footer`, `.footer-links`), adjust the `rewriter.on()` selector.

**KV TTL**: `expirationTtl` is set to exactly 365 days (31,536,000 seconds). Cloudflare KV enforces this server-side; the JSON payload's `expiresAt` field is a human-readable audit trail only.

**wrangler.toml binding**:
```toml
[[kv_namespaces]]
binding = "CCPA_OPT_OUTS"
id = "<your-kv-namespace-id>"
```

## Anti-patterns

- **Do not** rely solely on the client-side cookie for opt-out state. Cookies are clearable by users; KV is the authoritative record.
- **Do not** redirect `/api/ccpa/opt-out` to a third-party consent platform that itself shares data — that contradicts CCPA intent.
- **Do not** use `IP` alone as a user ID across sessions; it changes. Prefer session tokens or authenticated user IDs.
- **Do not** serve the opt-out confirmation page over HTTP (non-TLS) — the cookie uses `Secure` flag.
- **Do not** remove the CCPA link from pages behind a login wall — CCPA applies to all California residents regardless of login state.

## Gotchas

- **GPC is not universally required outside California** — check if your legal team wants to honor it globally or only for `CF-IPCountry: US` requests from California (no reliable state-level IP geolocation exists in standard CF headers; use `cf.regionCode` if available via Cloudflare Geo).
- **CPRA effective date**: Enforcement for "sharing" (not just "selling") began July 2023. Ensure `suppressSharing` logic covers behavioral advertising, not only explicit data sales.
- **HTMLRewriter `on('footer')`** matches the HTML5 `<footer>` element; if pages use `<div class="footer">`, the selector won't match — use attribute selectors or a `<body>` end-tag handler.
- **KV eventual consistency**: In rare cases, a write may not be immediately visible on a subsequent read from a different edge node. Cookie-based state provides immediate client-side consistency.
- **Re-consent timing**: CCPA allows re-requesting consent after 12 months. Implement a scheduled cleanup cron or let KV TTL handle expiry naturally.

## Verification

```bash
# 1. Test GPC signal detection
curl -H 'Sec-GPC: 1' https://example.com/ -I | grep X-CCPA-Opt-Out
# Expected: X-CCPA-Opt-Out: true

# 2. Explicit opt-out API
curl -X POST https://example.com/api/ccpa/opt-out \
  -H 'Content-Type: application/json' \
  -c cookies.txt -b cookies.txt
# Expected: {"success":true,"message":"Opt-out recorded for 12 months."}

# 3. Check opt-out status
curl https://example.com/api/ccpa/status -b cookies.txt
# Expected: {"optedOut":true,"source":"explicit",...}

# 4. Verify pixel removal (check response body for pixel domains)
curl https://example.com/ -b cookies.txt | grep -c 'pixel.facebook.com'
# Expected: 0

# 5. Verify CCPA link injection
curl https://example.com/ | grep 'Do Not Sell'
# Expected: line containing the opt-out link
```

## Related

- `documentation/categories/compliance/cookie-consent-banner.md` — GDPR consent banner; complements CCPA opt-out
- `documentation/categories/compliance/pii-detection-scrubber.md` — strips PII from logs before third-party forwarding
- `documentation/categories/compliance/gdpr-consent-logging.md` — consent audit trail pattern
- `documentation/categories/compliance/workers-data-subject-access-request.md` — DSAR fulfillment pipeline
- Cloudflare Workers HTMLRewriter docs

## Sources

- California Consumer Privacy Act (CCPA), Cal. Civ. Code § 1798.100 et seq.
- CPRA amendments effective January 1, 2023; enforcement July 1, 2023
- California AG CCPA regulations, 11 C.C.R. § 999.300
- W3C Global Privacy Control spec: https://globalprivacycontrol.org/
- Cloudflare Workers HTMLRewriter: https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- Cloudflare KV: https://developers.cloudflare.com/kv/
