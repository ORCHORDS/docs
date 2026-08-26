# Integrating Cloudflare Turnstile CAPTCHA in a Workers API

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your public-facing API endpoint (sign-up, contact form, password reset) is being abused by bots. You want server-side CAPTCHA validation without routing traffic through a third-party vendor. Cloudflare Turnstile provides a privacy-first alternative to reCAPTCHA, and its `siteverify` endpoint can be called directly from a Worker, keeping everything inside Cloudflare's network.

## Context

Turnstile has two client-side modes:

- **Managed** – Cloudflare decides when to show a challenge. Most visitors see nothing; only suspicious ones get a puzzle.
- **Invisible** – No visible widget; the challenge runs entirely in the background.

In both cases the browser receives a short-lived **token** (`cf-turnstile-response`). Your Worker must POST that token plus your **secret key** to `https://challenges.cloudflare.com/turnstile/v0/siteverify` before trusting the request.

Secrets are stored via `wrangler secret put` and injected into the Worker environment — never hard-code them in source.

## Solution

```typescript
// src/turnstile.ts

export interface Env {
  TURNSTILE_SECRET_KEY: string;
  TRUSTED_IPS: string; // comma-separated list, e.g. "1.2.3.4,5.6.7.8"
}

interface TurnstileVerifyResponse {
  success: boolean;
  challenge_ts?: string;
  hostname?: string;
  'error-codes'?: string[];
  action?: string;
  cdata?: string;
}

/**
 * Verify a Turnstile token server-side.
 * Returns the full siteverify payload so callers can inspect
 * `error-codes` for structured error handling.
 */
async function verifyTurnstileToken(
  token: string,
  secretKey: string,
  remoteIp?: string,
): Promise<TurnstileVerifyResponse> {
  const body = new URLSearchParams({
    secret: secretKey,
    response: token,
  });

  // Providing remoteip is optional but recommended — Turnstile uses it
  // for risk scoring; omit if you cannot reliably determine the client IP.
  if (remoteIp) {
    body.set('remoteip', remoteIp);
  }

  const res = await fetch(
    'https://challenges.cloudflare.com/turnstile/v0/siteverify',
    {
      method: 'POST',
      body,
    },
  );

  if (!res.ok) {
    throw new Error(`siteverify HTTP ${res.status}`);
  }

  return res.json<TurnstileVerifyResponse>();
}

/**
 * Parse the client IP from standard CF-forwarding headers.
 * CF Workers expose the real client IP in `CF-Connecting-IP`.
 */
function getClientIp(request: Request): string | undefined {
  return request.headers.get('CF-Connecting-IP') ?? undefined;
}

/**
 * Check whether the client IP appears in the TRUSTED_IPS env var.
 * Trusted IPs bypass Turnstile entirely — useful for internal tooling
 * or CI smoke tests that cannot complete a CAPTCHA.
 */
function isTrustedIp(ip: string | undefined, trustedIps: string): boolean {
  if (!ip) return false;
  return trustedIps
    .split(',')
    .map((s) => s.trim())
    .includes(ip);
}

/**
 * Main Worker handler — protect POST /register with Turnstile.
 */
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Only protect the registration endpoint.
    if (url.pathname !== '/register' || request.method !== 'POST') {
      return new Response('Not found', { status: 404 });
    }

    const clientIp = getClientIp(request);

    // Bypass CAPTCHA for trusted internal IPs (e.g. CI, admin VPN).
    if (isTrustedIp(clientIp, env.TRUSTED_IPS)) {
      return handleRegistration(request);
    }

    // Parse multipart form or JSON body.
    let token: string | null = null;
    const contentType = request.headers.get('content-type') ?? '';

    if (contentType.includes('application/json')) {
      const body = await request.json<{ 'cf-turnstile-response'?: string }>();
      token = body['cf-turnstile-response'] ?? null;
    } else {
      const form = await request.formData();
      token = form.get('cf-turnstile-response') as string | null;
    }

    if (!token) {
      return new Response(
        JSON.stringify({ error: 'missing_token', message: 'Turnstile token is required.' }),
        { status: 400, headers: { 'Content-Type': 'application/json' } },
      );
    }

    let verification: TurnstileVerifyResponse;

    try {
      verification = await verifyTurnstileToken(token, env.TURNSTILE_SECRET_KEY, clientIp);
    } catch (err) {
      console.error('Turnstile siteverify error:', err);
      return new Response(
        JSON.stringify({ error: 'verification_error', message: 'Could not verify CAPTCHA. Please try again.' }),
        { status: 503, headers: { 'Content-Type': 'application/json' } },
      );
    }

    if (!verification.success) {
      const codes = verification['error-codes'] ?? [];
      console.warn('Turnstile verification failed:', codes);
      return new Response(
        JSON.stringify({ error: 'captcha_failed', codes }),
        { status: 403, headers: { 'Content-Type': 'application/json' } },
      );
    }

    // Token is valid — proceed with business logic.
    return handleRegistration(request);
  },
};

async function handleRegistration(request: Request): Promise<Response> {
  // ... your actual registration logic here ...
  return new Response(JSON.stringify({ ok: true }), {
    status: 201,
    headers: { 'Content-Type': 'application/json' },
  });
}
```

**Client-side embed (managed mode):**

```html
<!-- Add to your HTML <head> -->
<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>

<!-- Place inside your <form> -->
<div
  class="cf-turnstile"
  data-sitekey="0x4AAAAAAAxxxxxxxxxxxxxxxx"
  data-theme="auto"
></div>
```

**Invisible mode (programmatic):**

```typescript
// Client-side TypeScript — call before form submit
declare const turnstile: {
  render: (container: string, options: object) => string;
  execute: (widgetId: string) => void;
  getResponse: (widgetId: string) => string | undefined;
};

const widgetId = turnstile.render('#turnstile-container', {
  sitekey: '0x4AAAAAAAxxxxxxxxxxxxxxxx',
  size: 'invisible',
  callback: (token: string) => {
    submitFormWithToken(token);
  },
});

document.querySelector('form')!.addEventListener('submit', (e) => {
  e.preventDefault();
  turnstile.execute(widgetId);
});
```

## Implementation Details

**Secret key storage:**

```bash
# Store secret — never commit to source control
wrangler secret put TURNSTILE_SECRET_KEY
# Enter the secret from the Turnstile dashboard when prompted

# TRUSTED_IPS is less sensitive but still use a secret or wrangler.toml var
wrangler secret put TRUSTED_IPS
```

**wrangler.toml:**

```toml
[vars]
# Public site key is safe to commit
TURNSTILE_SITE_KEY = "0x4AAAAAAAxxxxxxxxxxxxxxxx"
# TURNSTILE_SECRET_KEY and TRUSTED_IPS come from `wrangler secret put`
```

**Retry logic for siteverify:**

```typescript
async function verifyWithRetry(
  token: string,
  secretKey: string,
  maxAttempts = 3,
): Promise<TurnstileVerifyResponse> {
  let lastError: Error | undefined;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const result = await verifyTurnstileToken(token, secretKey);
      return result;
    } catch (err) {
      lastError = err as Error;
      if (attempt < maxAttempts) {
        // Exponential backoff: 100ms, 200ms
        await new Promise((r) => setTimeout(r, 100 * attempt));
      }
    }
  }
  throw lastError;
}
```

## Anti-patterns

- **Trusting the token client-side only.** The token must always be verified server-side via `siteverify`. A bot can trivially forge a form field.
- **Reusing tokens.** Each token is single-use. Cache the verified result by a session ID, not the token itself.
- **Hard-coding the secret key** in `wrangler.toml` or source files. Use `wrangler secret put`.
- **Failing open on `siteverify` errors.** Unless you have a specific business reason, return 503 and ask the user to retry rather than letting the request through.
- **Not passing `remoteip`.** Without it, Turnstile's risk scoring is less accurate, increasing both false positives and false negatives.

## Gotchas

- **Test keys:** Cloudflare provides special site/secret key pairs for testing that always pass or always fail — use them in staging/CI environments.
  - Always-pass sitekey: `1x00000000000000000000AA` / secret: <redacted-secret>
  - Always-fail sitekey: `2x00000000000000000000AB` / secret: <redacted-secret>
- **Token expiry:** Tokens expire after ~5 minutes. If your form submission latency exceeds this, Turnstile will return `timeout-or-duplicate`.
- **CSP headers:** The Turnstile widget requires `script-src challenges.cloudflare.com` and `frame-src challenges.cloudflare.com` in your Content-Security-Policy.
- **`CF-Connecting-IP` spoofing:** This header is set by Cloudflare and cannot be spoofed by the client when traffic arrives through Cloudflare's edge. If you're running the Worker in local dev via `wrangler dev`, the header may be absent.

## Verification

```bash
# Use the always-pass test secret to verify your Worker logic
curl -X POST https://your-worker.example.com/register \
  -H 'Content-Type: application/json' \
  -d '{"cf-turnstile-response": "XXXX.DUMMY.TOKEN.XXXX"}'
# Expect: {"ok": true} with status 201 when using test keys

# Without a token — expect 400
curl -X POST https://your-worker.example.com/register \
  -H 'Content-Type: application/json' \
  -d '{}'
```

## Related

- `workers-rate-limiting-with-kv.md` — combine Turnstile with rate limiting for defense in depth
- `workers-secrets-management.md` — best practices for `wrangler secret put`
- Cloudflare Pages Functions variant: place verification logic in `functions/api/register.ts`

## Sources

- https://developers.cloudflare.com/turnstile/
- https://developers.cloudflare.com/turnstile/get-started/server-side-validation/
- https://developers.cloudflare.com/turnstile/reference/testing/
- https://developers.cloudflare.com/workers/configuration/secrets/
