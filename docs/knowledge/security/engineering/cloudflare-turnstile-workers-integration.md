# Cloudflare Turnstile Integration in Workers: Bot-Proof API Endpoints

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A public-facing Cloudflare Worker handles form submissions, account registrations, password resets, or free-tier API calls. Without a bot-detection layer, automated scripts can:

- Exhaust rate limits designed for human users
- Spam registration flows, polluting D1 user tables
- Enumerate valid email addresses at low cost
- Trigger expensive downstream API calls (AI inference, email sends, SMS OTPs)

Traditional CAPTCHAs add friction for real users. Cloudflare Turnstile offers a non-interactive, privacy-preserving challenge that resolves invisibly for most legitimate users while blocking bots. This article covers integrating Turnstile token validation inside a Worker with correct security boundaries.

## Context

Turnstile works in two phases:

1. **Client side**: The browser loads Turnstile's widget JS, which runs a challenge (device signals, interaction entropy, proof-of-work puzzles). On success it returns a short-lived `cf-turnstile-response` token.
2. **Server side**: The Worker sends that token to `https://challenges.cloudflare.com/turnstile/v0/siteverify` with the site's secret key. The response confirms the token is valid, unused, and not expired.

The secret key must never leave the Worker runtime. A forged or replayed token must be rejected. A missing token must be a hard 403, not a soft warning.

Turnstile has three widget modes:

| Mode | User interaction | Best for |
|------|-----------------|----------|
| Managed | Auto (invisible or click) | Most forms |
| Non-interactive | Always invisible | Low-friction APIs |
| Invisible | Fully silent | Embedded flows |

## Setting Up the Turnstile Widget (Client Side)

Add the script and the widget div to every page that POSTs to your Worker:

```html
<!-- In your HTML page -->
<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>

<form id="signup-form" action="/api/register" method="POST">
  <input type="email" name="email" required />
  <input type="password" name="password" required autocomplete="new-password" />

  <!-- Turnstile renders here; token is injected into cf-turnstile-response field -->
  <div class="cf-turnstile"
       data-sitekey="YOUR_SITE_KEY"
       data-callback="onTurnstileSuccess"
       data-error-callback="onTurnstileError"
       data-theme="auto">
  </div>

  <button type="submit" id="submit-btn" disabled>Create account</button>
</form>

<script>
function onTurnstileSuccess(token) {
  // Only enable submit once Turnstile has issued a token
  document.getElementById('submit-btn').disabled = false;
}

function onTurnstileError() {
  // Surface a user-friendly message; never silently fail
  document.getElementById('submit-btn').disabled = true;
  alert('Bot check failed. Please refresh the page and try again.');
}
</script>
```

For SPAs using fetch, retrieve the token programmatically before submission:

```javascript
// SPA pattern — read the widget token before calling the API
async function submitRegistration(email, password) {
  const token = document.querySelector('[name="cf-turnstile-response"]').value;
  if (!token) throw new Error('Turnstile token missing');

  const res = await fetch('/api/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, turnstileToken: token }),
  });

  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.error ?? 'Registration failed');
  }
  return res.json();
}
```

## Server-Side Token Validation in Workers

Create a reusable `verifyTurnstile` helper. Never inline this logic or skip it conditionally.

```typescript
// src/lib/turnstile.ts

export interface TurnstileOutcome {
  success: boolean;
  errorCodes: string[];
  hostname?: string;
  action?: string;
  cdata?: string;
}

/**
 * Verify a Turnstile token with Cloudflare's siteverify endpoint.
 *
 * @param token   The cf-turnstile-response value from the request body.
 * @param secret  The TURNSTILE_SECRET_KEY binding from wrangler.toml.
 * @param ip      The client IP (CF-Connecting-IP header). Passing it tightens
 *                Turnstile's signal analysis but is optional.
 */
export async function verifyTurnstile(
  token: string,
  secret: string,
  ip?: string,
): Promise<TurnstileOutcome> {
  if (!token || typeof token !== 'string' || token.length > 2048) {
    return { success: false, errorCodes: ['invalid-input-response'] };
  }

  const body = new URLSearchParams({ secret, response: token });
  if (ip) body.set('remoteip', ip);

  const resp = await fetch(
    'https://challenges.cloudflare.com/turnstile/v0/siteverify',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
    },
  );

  if (!resp.ok) {
    // Treat network/upstream errors as a failed challenge, not a bypass
    return { success: false, errorCodes: ['internal-error'] };
  }

  const data = await resp.json<{
    success: boolean;
    'error-codes': string[];
    hostname: string;
    action?: string;
    cdata?: string;
  }>();

  return {
    success: data.success,
    errorCodes: data['error-codes'] ?? [],
    hostname: data.hostname,
    action: data.action,
    cdata: data.cdata,
  };
}
```

Wire it into the registration handler:

```typescript
// src/handlers/register.ts
import { verifyTurnstile } from '../lib/turnstile';

interface Env {
  TURNSTILE_SECRET_KEY: string;
  DB: D1Database;
}

export async function handleRegister(req: Request, env: Env): Promise<Response> {
  const clientIp = req.headers.get('CF-Connecting-IP') ?? undefined;

  let body: { email?: string; password?: string; turnstileToken?: string };
  try {
    body = await req.json();
  } catch {
    return new Response(JSON.stringify({ error: 'Invalid JSON' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // 1. Validate Turnstile FIRST — before any business logic or DB touch
  const token = body.turnstileToken ?? '';
  const outcome = await verifyTurnstile(token, env.TURNSTILE_SECRET_KEY, clientIp);

  if (!outcome.success) {
    console.warn('Turnstile failure', { codes: outcome.errorCodes, ip: clientIp });
    return new Response(
      JSON.stringify({ error: 'Bot challenge failed', codes: outcome.errorCodes }),
      { status: 403, headers: { 'Content-Type': 'application/json' } },
    );
  }

  // 2. Optionally bind the token to the expected hostname / action
  const expectedHostname = 'app.example.com';
  if (outcome.hostname && outcome.hostname !== expectedHostname) {
    return new Response(JSON.stringify({ error: 'Token hostname mismatch' }), {
      status: 403,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // 3. Proceed with validated business logic
  const { email, password } = body;
  if (!email || !password) {
    return new Response(JSON.stringify({ error: 'Missing fields' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // ... hash password, insert user, etc.
  return new Response(JSON.stringify({ success: true }), {
    status: 201,
    headers: { 'Content-Type': 'application/json' },
  });
}
```

## Wrangler Configuration and Secret Binding

Store the secret key as a Workers secret, never in `wrangler.toml` plaintext:

```toml
# wrangler.toml — site key is public, goes here
[vars]
TURNSTILE_SITE_KEY = "0x4AAAAAAA..."  # Public — safe to commit

# Secret key is NOT here. Add it via CLI:
# wrangler secret put TURNSTILE_SECRET_KEY
```

```bash
# One-time setup per environment
wrangler secret put TURNSTILE_SECRET_KEY --env production
# Paste the secret when prompted; it is stored encrypted in Workers secrets

# Verify the secret is registered (value is never shown)
wrangler secret list --env production
```

For local development use `.dev.vars` (git-ignored):

```ini
# .dev.vars — never commit this file
TURNSTILE_SECRET_KEY=1x0000000000000000000000000000000AA  # Test secret key
```

Cloudflare provides dedicated test keys for local dev:

| Site key | Behavior |
|----------|----------|
| `1x00000000000000000000AA` | Always passes |
| `2x00000000000000000000AB` | Always blocks |
| `3x00000000000000000000FF` | Forces interactive challenge |

## Anti-patterns

- **Validating on the client only**: JavaScript can be bypassed. The `siteverify` call must always happen in the Worker, never in the browser.
- **Caching siteverify responses**: Turnstile tokens are one-time-use. Caching a `success: true` response allows replay attacks. Always call `siteverify` for each submission.
- **Skipping validation in staging**: Bots target staging environments. Use the "always pass" test site key in staging rather than removing validation.
- **Returning 200 on bot detection**: A vague success response that silently discards the submission trains attackers to retry. Return 403 with a clear `error` field.
- **Not binding to hostname**: Without hostname verification, a token obtained from a different Turnstile site key can be replayed against your endpoint. Always assert `outcome.hostname`.
- **Exposing the secret key in `wrangler.toml`**: The `[vars]` section is committed to source control. Always use `wrangler secret put` or `.dev.vars` for the secret key.

## Gotchas

- **Token lifetime**: Turnstile tokens expire after roughly 300 seconds. Mobile users who leave a form open too long will get a stale token and a 403. Re-render the widget on retry to obtain a fresh token.
- **Multiple widgets on one page**: Each widget produces its own token. If you have a login widget and a newsletter widget on the same page, disambiguate them by reading the correct `name` attribute or widget container ID.
- **`CF-Connecting-IP` in local dev**: `wrangler dev` does not populate this header. Guard the `remoteip` parameter with a null check so local runs do not break.
- **Rate limiting siteverify calls**: `challenges.cloudflare.com` has no published rate limit, but Turnstile tokens are free within your account's usage tier. Monitor via the Turnstile dashboard for unexpected spikes.
- **Workers subrequest count**: Each `siteverify` call costs one outbound subrequest. Workers on the free plan have a subrequest limit per invocation. Batch-heavy endpoints (bulk import) should verify tokens before spawning further subrequests.

## Verification

```bash
# 1. Confirm the secret is set
wrangler secret list --env production | grep TURNSTILE_SECRET_KEY

# 2. Smoke-test with the "always block" test key — expect 403
curl -s -X POST https://your-worker.workers.dev/api/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"a@b.com","password":"x","turnstileToken":"XXXX.DUMMY.TOKEN.XXXX"}' \
  | jq .error

# 3. Test with a missing token — must also return 403
curl -s -X POST https://your-worker.workers.dev/api/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"a@b.com","password":"x"}' \
  | jq .error

# 4. Check Turnstile analytics dashboard for solve rate trends
# Cloudflare Dashboard -> Turnstile -> your sitekey -> Analytics
```

## Related

- `cloudflare-bot-management-abuse-prevention.md`
- `rate-limiting-per-user-d1-durable-objects.md`
- `account-enumeration-prevention.md`
- `credential-stuffing-account-takeover-defense.md`

## Sources

- Cloudflare Turnstile documentation: https://developers.cloudflare.com/turnstile/
- Turnstile server-side validation: https://developers.cloudflare.com/turnstile/get-started/server-side-validation/
- Test keys and site keys: https://developers.cloudflare.com/turnstile/troubleshooting/testing/
- Workers secrets: https://developers.cloudflare.com/workers/configuration/secrets/
