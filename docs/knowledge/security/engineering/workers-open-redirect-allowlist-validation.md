# Open Redirect Prevention with KV Allowlist Validation in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker issues redirects after login, email-verification, or OAuth callbacks via a `?redirect=` query parameter. An attacker crafts a URL like `https://your-app.workers.dev/login?redirect=https://evil.example.com` and sends it to users in phishing emails. Because the link starts with your trusted domain, users click it and are silently bounced to the attacker's site. You need server-side validation against a KV-stored allowlist, `data:` / `javascript:` URL rejection, and D1-backed audit logging of every rejected attempt.

## Context

Open redirects are a OWASP Top-10 class vulnerability (A01 Broken Access Control). The fix is:
1. Parse the destination URL server-side.
2. Accept only origins on a pre-approved allowlist (same origin is always allowed).
3. Reject any scheme other than `https:` (and optionally `http:` for localhost dev).
4. Log rejected attempts with request metadata to D1 for SOC review.

Runtime: Cloudflare Workers (TypeScript)
Storage: KV (allowlist), D1 (audit log)

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS redirect_audit_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          INTEGER NOT NULL,
  ip          TEXT,
  user_agent  TEXT,
  raw_redirect TEXT NOT NULL,
  reason      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_redirect_ts ON redirect_audit_log(ts);
```

## KV Allowlist Format

```bash
# KV key: "redirect-allowlist"
# KV value: JSON array of allowed origin strings (scheme + host, no trailing slash)
wrangler kv key put --namespace-id=<id> "redirect-allowlist" \
  '["https://app.example.com","https://docs.example.com","https://accounts.example.com"]'
```

## Env Types

```typescript
// src/types.ts
export interface Env {
  REDIRECT_ALLOWLIST: KVNamespace;
  DB: D1Database;
}
```

## Core Validation Logic

```typescript
// src/lib/redirect-validator.ts

const DANGEROUS_SCHEMES = new Set([
  'javascript', 'data', 'vbscript', 'file', 'blob',
]);

export interface ValidationResult {
  safe: boolean;
  reason?: string;
  normalizedUrl?: string;
}

/**
 * Validate a redirect destination URL.
 *
 * @param raw         The raw string from the query parameter.
 * @param requestUrl  The current request URL (used to derive the "same origin").
 * @param allowlist   Trusted external origins (e.g. ["https://docs.example.com"]).
 */
export function validateRedirectUrl(
  raw: string,
  requestUrl: URL,
  allowlist: string[]
): ValidationResult {
  if (!raw || raw.trim() === '') {
    return { safe: false, reason: 'empty redirect value' };
  }

  // Normalise: trim and decode once to catch double-encoding tricks
  let decoded: string;
  try {
    decoded = decodeURIComponent(raw.trim());
  } catch {
    return { safe: false, reason: 'malformed percent-encoding' };
  }

  // Reject dangerous scheme prefixes before URL parsing
  // URL() would accept "javascript:alert(1)" as a valid URL
  const lc = decoded.toLowerCase();
  for (const scheme of DANGEROUS_SCHEMES) {
    if (lc.startsWith(scheme + ':')) {
      return { safe: false, reason: `dangerous scheme: ${scheme}` };
    }
  }

  // Attempt to parse as an absolute URL
  let target: URL;
  try {
    target = new URL(decoded, requestUrl.origin); // relative URLs resolve to same origin
  } catch {
    return { safe: false, reason: 'unparseable URL' };
  }

  // Only allow https (and http for localhost)
  if (target.protocol !== 'https:') {
    const isLocalhost =
      target.hostname === 'localhost' || target.hostname === '127.0.0.1';
    if (!(isLocalhost && target.protocol === 'http:')) {
      return { safe: false, reason: `disallowed protocol: ${target.protocol}` };
    }
  }

  // Same origin is always safe
  if (target.origin === requestUrl.origin) {
    return { safe: true, normalizedUrl: target.toString() };
  }

  // External origin must be on the allowlist
  if (allowlist.includes(target.origin)) {
    return { safe: true, normalizedUrl: target.toString() };
  }

  return {
    safe: false,
    reason: `origin not in allowlist: ${target.origin}`,
  };
}
```

## Audit Logger

```typescript
// src/lib/redirect-audit.ts
import type { Env } from '../types';

export async function logRejectedRedirect(
  env: Env,
  request: Request,
  rawRedirect: string,
  reason: string
): Promise<void> {
  const ip = request.headers.get('CF-Connecting-IP') ?? 'unknown';
  const userAgent = request.headers.get('User-Agent') ?? '';

  await env.DB.prepare(
    `INSERT INTO redirect_audit_log (ts, ip, user_agent, raw_redirect, reason)
     VALUES (?, ?, ?, ?, ?)`
  )
    .bind(Date.now(), ip, userAgent.slice(0, 512), rawRedirect.slice(0, 2048), reason)
    .run();
}
```

## Worker Handler

```typescript
// src/handlers/safe-redirect.ts
import type { Env } from '../types';
import { validateRedirectUrl } from '../lib/redirect-validator';
import { logRejectedRedirect } from '../lib/redirect-audit';

const FALLBACK_URL = '/';

export async function handleSafeRedirect(
  request: Request,
  env: Env
): Promise<Response> {
  const requestUrl = new URL(request.url);
  const rawRedirect = requestUrl.searchParams.get('redirect') ?? '';

  // Load allowlist from KV (cached at the edge; TTL set by KV replication)
  const allowlist = (await env.REDIRECT_ALLOWLIST.get('redirect-allowlist', 'json') as
    | string[]
    | null) ?? [];

  const result = validateRedirectUrl(rawRedirect, requestUrl, allowlist);

  if (!result.safe) {
    // Fire-and-forget audit log (don't await so it doesn't delay the response)
    env.DB && void logRejectedRedirect(env, request, rawRedirect, result.reason!);

    // Redirect to safe fallback
    return Response.redirect(new URL(FALLBACK_URL, requestUrl.origin).toString(), 302);
  }

  return Response.redirect(result.normalizedUrl!, 302);
}
```

## Unit Tests

```typescript
// src/lib/redirect-validator.test.ts
import { describe, it, expect } from 'vitest';
import { validateRedirectUrl } from './redirect-validator';

const BASE = new URL('https://app.example.com');
const ALLOWLIST = ['https://docs.example.com'];

describe('validateRedirectUrl', () => {
  it('accepts same-origin relative path', () => {
    expect(validateRedirectUrl('/dashboard', BASE, ALLOWLIST).safe).toBe(true);
  });

  it('accepts same-origin absolute URL', () => {
    expect(validateRedirectUrl('https://app.example.com/profile', BASE, ALLOWLIST).safe).toBe(true);
  });

  it('accepts allowlisted external origin', () => {
    expect(validateRedirectUrl('https://docs.example.com/guide', BASE, ALLOWLIST).safe).toBe(true);
  });

  it('rejects unlisted external origin', () => {
    const r = validateRedirectUrl('https://evil.example.com', BASE, ALLOWLIST);
    expect(r.safe).toBe(false);
    expect(r.reason).toContain('not in allowlist');
  });

  it('rejects javascript: URL', () => {
    const r = validateRedirectUrl('javascript:alert(1)', BASE, ALLOWLIST);
    expect(r.safe).toBe(false);
    expect(r.reason).toContain('dangerous scheme');
  });

  it('rejects data: URL', () => {
    expect(validateRedirectUrl('data:text/html,<h1>phish</h1>', BASE, ALLOWLIST).safe).toBe(false);
  });

  it('rejects double-encoded javascript:', () => {
    expect(validateRedirectUrl('javascript%3Aalert(1)', BASE, ALLOWLIST).safe).toBe(false);
  });

  it('rejects http (non-localhost)', () => {
    expect(validateRedirectUrl('http://evil.example.com', BASE, ALLOWLIST).safe).toBe(false);
  });

  it('accepts http://localhost in dev', () => {
    expect(validateRedirectUrl('http://localhost:3000/page', BASE, ALLOWLIST).safe).toBe(true);
  });
});
```

## Anti-patterns

- **String-prefix matching** — `url.startsWith('https://app.example.com')` can be bypassed with `https://app.example.com.evil.com`; always compare `URL.origin`.
- **Allowlisting paths, not origins** — an attacker can craft `https://trusted.com@evil.com`; parse with `URL()` and compare `.origin`.
- **Trusting `Referer` header** — it is user-controlled and easily spoofed.
- **Silently dropping the redirect and returning 200** — use an explicit fallback redirect so the user knows something happened.
- **Logging to console only** — D1 audit logs survive across deployments and can be queried by security teams.

## Gotchas

- `new URL(relative, base)` resolves relative URLs against the base origin — this is intentional and means `/dashboard` is always same-origin.
- The `URL()` constructor in Workers is the WHATWG URL standard; it normalises `HTTPS:` to `https:`, so compare lower-cased protocols.
- KV reads in Workers are network calls; wrap in a try/catch and fall back to a default-deny empty allowlist on KV errors.
- D1 write latency is acceptable for audit logs (fire-and-forget with `void`); do NOT await it in the response path.

## Verification

```bash
# Test valid same-origin redirect
curl -si 'https://your-app.workers.dev/callback?redirect=%2Fdashboard' | grep location
# Expected: location: https://your-app.workers.dev/dashboard

# Test open redirect attempt
curl -si 'https://your-app.workers.dev/callback?redirect=https%3A%2F%2Fevil.com' | grep location
# Expected: location: https://your-app.workers.dev/

# Inspect audit log
wrangler d1 execute app-db \
  --command "SELECT ts, ip, raw_redirect, reason FROM redirect_audit_log ORDER BY ts DESC LIMIT 10;"
```

## Related

- `workers-session-fixation-prevention.md` — open redirects are commonly chained with session fixation
- `workers-clickjacking-x-frame-options.md` — complementary header hardening
- OWASP Unvalidated Redirects: https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html

## Sources

- WHATWG URL Living Standard: https://url.spec.whatwg.org/
- Cloudflare KV API: https://developers.cloudflare.com/kv/api/
- Cloudflare D1 API: https://developers.cloudflare.com/d1/worker-api/
