# Clickjacking Prevention with X-Frame-Options and CSP in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Workers-served HTML pages can be embedded in a hidden `<iframe>` on an attacker-controlled site. The attacker overlays deceptive UI on top and tricks users into clicking buttons they cannot see — transferring funds, changing passwords, or authorising OAuth grants. You need per-route header logic: deny framing globally, but allow known embed partners on specific routes.

## Context

Two independent mechanisms defend against clickjacking:

1. **`X-Frame-Options` (XFO)** — legacy, broadly supported, only two values matter: `DENY` and `SAMEORIGIN`.
2. **`Content-Security-Policy: frame-ancestors`** — modern, takes an allowlist of origins, supersedes XFO in browsers that support CSP Level 2+.

Send both headers: XFO covers older browsers; CSP `frame-ancestors` provides fine-grained control. Cloudflare Workers intercept every response so adding headers requires no origin-server changes.

## Middleware: Global Deny

```typescript
// src/middleware/anti-clickjacking.ts

export interface FramePolicy {
  /** Paths where a specific origin may embed this page. */
  allowlist: Map<string, string[]>; // pathname prefix -> allowed origins
}

/**
 * Adds X-Frame-Options and CSP frame-ancestors to every HTML response.
 * Routes in `policy.allowlist` get a targeted allowlist instead of DENY.
 */
export function applyFrameHeaders(
  response: Response,
  requestPath: string,
  policy: FramePolicy
): Response {
  const contentType = response.headers.get('content-type') ?? '';
  // Only inject on HTML responses
  if (!contentType.includes('text/html')) {
    return response;
  }

  const mutable = new Response(response.body, response);
  const allowedOrigins = resolveAllowedOrigins(requestPath, policy.allowlist);

  if (allowedOrigins.length === 0) {
    // Global deny
    mutable.headers.set('X-Frame-Options', 'DENY');
    mutable.headers.set(
      'Content-Security-Policy',
      buildCsp(response.headers.get('Content-Security-Policy'), "frame-ancestors 'none'")
    );
  } else {
    // Per-route allowlist — XFO cannot express multiple origins, so omit it
    // and rely solely on CSP frame-ancestors.
    mutable.headers.delete('X-Frame-Options');
    const ancestors = allowedOrigins.join(' ');
    mutable.headers.set(
      'Content-Security-Policy',
      buildCsp(
        response.headers.get('Content-Security-Policy'),
        `frame-ancestors 'self' ${ancestors}`
      )
    );
  }

  return mutable;
}

/** Find the most-specific prefix match in the allowlist. */
function resolveAllowedOrigins(
  path: string,
  allowlist: Map<string, string[]>
): string[] {
  let best: string[] = [];
  let bestLen = -1;
  for (const [prefix, origins] of allowlist) {
    if (path.startsWith(prefix) && prefix.length > bestLen) {
      best = origins;
      bestLen = prefix.length;
    }
  }
  return best;
}

/**
 * Merge a new directive into an existing CSP string.
 * If `frame-ancestors` already exists it is replaced; otherwise the directive
 * is appended.
 */
function buildCsp(existing: string | null, directive: string): string {
  if (!existing) return directive;
  const directives = existing
    .split(';')
    .map((d) => d.trim())
    .filter(Boolean);
  const idx = directives.findIndex((d) => d.startsWith('frame-ancestors'));
  if (idx >= 0) {
    directives[idx] = directive;
  } else {
    directives.push(directive);
  }
  return directives.join('; ');
}
```

## Env Types

```typescript
// src/types.ts
export interface Env {
  FRAME_ALLOWLIST_KV: KVNamespace; // optional: load allowlist from KV
  // ... other bindings
}
```

## Worker Entry Point

```typescript
// src/index.ts
import { applyFrameHeaders, type FramePolicy } from './middleware/anti-clickjacking';
import type { Env } from './types';

/**
 * Load per-route allowlist from KV so it can be updated without redeployment.
 * KV key: "frame-allowlist"
 * KV value: JSON object { "/embed/widget": ["https://partner.example.com"] }
 */
async function loadPolicy(env: Env): Promise<FramePolicy> {
  const raw = await env.FRAME_ALLOWLIST_KV.get('frame-allowlist', 'json') as
    | Record<string, string[]>
    | null;

  const allowlist = new Map<string, string[]>(Object.entries(raw ?? {}));
  return { allowlist };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // 1. Route to upstream / cache / etc.
    const upstreamResponse = await handleRequest(request, env);

    // 2. Apply frame headers
    const policy = await loadPolicy(env);
    const path = new URL(request.url).pathname;
    return applyFrameHeaders(upstreamResponse, path, policy);
  },
};

async function handleRequest(request: Request, _env: Env): Promise<Response> {
  // Placeholder: your real routing logic here
  return new Response('<html><body>Hello</body></html>', {
    headers: { 'content-type': 'text/html; charset=utf-8' },
  });
}
```

## Updating the Allowlist at Runtime

```bash
# Allow https://partner.example.com to embed /embed/widget
wrangler kv key put --namespace-id=<id> "frame-allowlist" \
  '{"/ embed/widget":["https://partner.example.com"]}'

# Verify
wrangler kv key get --namespace-id=<id> "frame-allowlist"
```

## Unit Tests

```typescript
// src/middleware/anti-clickjacking.test.ts
import { describe, it, expect } from 'vitest';
import { applyFrameHeaders, type FramePolicy } from './anti-clickjacking';

function htmlResponse(extraHeaders: Record<string, string> = {}): Response {
  return new Response('<html></html>', {
    headers: { 'content-type': 'text/html', ...extraHeaders },
  });
}

describe('applyFrameHeaders', () => {
  const denyPolicy: FramePolicy = { allowlist: new Map() };

  it('adds DENY and frame-ancestors none on unmatched path', () => {
    const res = applyFrameHeaders(htmlResponse(), '/login', denyPolicy);
    expect(res.headers.get('X-Frame-Options')).toBe('DENY');
    expect(res.headers.get('Content-Security-Policy')).toContain("frame-ancestors 'none'");
  });

  it('uses allowlist on matched prefix', () => {
    const policy: FramePolicy = {
      allowlist: new Map([['/embed', ['https://partner.example.com']]]),
    };
    const res = applyFrameHeaders(htmlResponse(), '/embed/widget', policy);
    expect(res.headers.get('X-Frame-Options')).toBeNull();
    const csp = res.headers.get('Content-Security-Policy') ?? '';
    expect(csp).toContain('https://partner.example.com');
    expect(csp).toContain("frame-ancestors 'self'");
  });

  it('does not modify non-HTML responses', () => {
    const json = new Response('{"ok":true}', {
      headers: { 'content-type': 'application/json' },
    });
    const res = applyFrameHeaders(json, '/api/data', denyPolicy);
    expect(res.headers.get('X-Frame-Options')).toBeNull();
  });

  it('merges with existing CSP', () => {
    const res = applyFrameHeaders(
      htmlResponse({ 'content-security-policy': "default-src 'self'" }),
      '/page',
      denyPolicy
    );
    const csp = res.headers.get('Content-Security-Policy') ?? '';
    expect(csp).toContain("default-src 'self'");
    expect(csp).toContain("frame-ancestors 'none'");
  });
});
```

## Anti-patterns

- **Setting only `X-Frame-Options: SAMEORIGIN`** — this allows any page on the same origin to embed the page, which may be too permissive for sensitive flows like payments or auth.
- **Relying solely on JavaScript frame-busting** — `if (top !== self) top.location = self.location` is bypassable with `sandbox` attribute on the iframe.
- **Serving XFO on API routes** — wastes bytes; clickjacking targets HTML, not JSON.
- **Hardcoding the allowlist in Worker code** — a runtime KV read lets you update trusted partners without a deploy.
- **Setting `frame-ancestors *`** — explicitly allows any origin to embed the page; equivalent to no protection.

## Gotchas

- `X-Frame-Options` cannot express multiple allowed origins; use CSP `frame-ancestors` for that.
- `Content-Security-Policy` with `frame-ancestors` is ignored by IE 11; send both headers for legacy coverage.
- Cloudflare's **Auto-Minify** and **HTML Rewriting** may add `X-Frame-Options: SAMEORIGIN` themselves — check Cloudflare dashboard settings and override explicitly.
- When the Worker sits behind **Cloudflare Pages**, the platform already injects `X-Frame-Options: DENY`; verify you are not sending conflicting values.

## Verification

```bash
# Check live headers
curl -si https://your-app.workers.dev/login | grep -i 'x-frame\|content-security'
# Expected output:
# x-frame-options: DENY
# content-security-policy: frame-ancestors 'none'

# Check an allowlisted route
curl -si https://your-app.workers.dev/embed/widget | grep -i 'content-security'
# Expected output:
# content-security-policy: frame-ancestors 'self' https://partner.example.com

# Run unit tests
npx vitest run src/middleware/anti-clickjacking.test.ts
```

## Related

- `workers-passkey-webauthn-registration.md` — protect passkey registration page from framing
- `workers-open-redirect-allowlist-validation.md` — complementary header hardening
- OWASP Clickjacking Defence Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Clickjacking_Defense_Cheat_Sheet.html

## Sources

- MDN X-Frame-Options: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Frame-Options
- MDN CSP frame-ancestors: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy/frame-ancestors
- Cloudflare Workers Response headers: https://developers.cloudflare.com/workers/runtime-apis/response/
