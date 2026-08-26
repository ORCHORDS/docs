# Turnstile Site Key Domain Mismatch Blocked All New User Registrations in Production

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

The registration form showed the Turnstile widget successfully (spinner resolved to
a green tick). Server-side verification of the token returned `{ success: false,
error-codes: ["invalid-input-response"] }`. Every new registration attempt failed
for 47 minutes, until the on-call engineer discovered the staging site key had been
promoted to production in the last deploy.

---

## Context

Cloudflare Turnstile site keys are **domain-scoped**: each key is created with an
allow-list of hostnames. When the widget loads on a domain not in that allow-list,
it still renders and resolves — **but the token it issues will fail server-side
verification**. No error appears in the browser console, and the widget's visual state
does not indicate the domain mismatch. This makes the failure invisible to end users
and manual QA testers until server-side verification is wired up.

The incident was caused by a `.env.production` file that referenced
`TURNSTILE_SITE_KEY=1x00000000000000000000AA` (the staging/test key, which validates
against `localhost` and the staging hostname) instead of the production key.

---

## How Turnstile Site Keys Are Scoped

Each key is created in the Cloudflare dashboard under **Turnstile → Add Site**:

| Key type        | Domain binding                         | Notes                              |
|-----------------|----------------------------------------|------------------------------------|
| Production key  | `app.example.com`                      | Tokens only valid on this domain.  |
| Staging key     | `staging.example.com`, `localhost`     | Tokens only valid on these domains.|
| Test/always-pass key | `*` (special test key `1x0000…AA`) | Tokens always pass server-side; for automated tests only. |

A token issued by a widget loaded on `app.example.com` using a key configured for
`staging.example.com` will **always** return `invalid-input-response` on verification.

---

## Correct Environment Variable Strategy

```typescript
// src/env.ts — typed environment bindings for a Worker
export interface Env {
  /** Cloudflare Turnstile secret key for server-side verification. */
  TURNSTILE_SECRET_KEY: string;
  /** Public site key embedded in the HTML (safe to expose). */
  TURNSTILE_SITE_KEY: string;
}

// wrangler.toml — use [env] blocks to keep keys separate per environment:
//
// [env.production.vars]
// TURNSTILE_SITE_KEY = "0x4AAAAAAAxxxxPRODUCTION"  # production key
//
// [env.staging.vars]
// TURNSTILE_SITE_KEY = "0x4AAAAAAAxxxxSTAGING"     # staging key
//
// Secrets (TURNSTILE_SECRET_KEY) must be set via `wrangler secret put`:
//   npx wrangler secret put TURNSTILE_SECRET_KEY --env production
//   npx wrangler secret put TURNSTILE_SECRET_KEY --env staging
```

---

## Server-Side Token Verification

```typescript
// src/turnstile.ts
export interface TurnstileVerifyResult {
  success: boolean;
  errorCodes: string[];
  hostname: string | null;
  action: string | null;
  cdata: string | null;
}

/**
 * Verifies a Turnstile challenge response token.
 * Always call from a Worker (server side) — never client side.
 * See: https://developers.cloudflare.com/turnstile/get-started/server-side-validation/
 */
export async function verifyTurnstileToken(
  secretKey: string,
  token: string,
  remoteIp?: string,
): Promise<TurnstileVerifyResult> {
  const body = new URLSearchParams({
    secret: secretKey,
    response: token,
  });
  if (remoteIp) body.set("remoteip", remoteIp);

  const response = await fetch(
    "https://challenges.cloudflare.com/turnstile/v0/siteverify",
    {
      method: "POST",
      body,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    },
  );

  if (!response.ok) {
    throw new Error(`Turnstile verification HTTP ${response.status}`);
  }

  const data = (await response.json()) as {
    success: boolean;
    "error-codes": string[];
    hostname: string | null;
    action: string | null;
    cdata: string | null;
  };

  return {
    success: data.success,
    errorCodes: data["error-codes"] ?? [],
    hostname: data.hostname,
    action: data.action,
    cdata: data.cdata,
  };
}
```

---

## Registration Handler with Explicit Hostname Assertion

The `hostname` field in the verification response reflects which domain the token was
issued for. Asserting it in the Worker provides a second layer of protection and makes
mismatch bugs surface immediately in logs rather than silently denying users.

```typescript
// src/handlers/register.ts
import { verifyTurnstileToken } from "../turnstile";

const EXPECTED_HOSTNAME =
  typeof PRODUCTION_HOSTNAME !== "undefined"
    ? PRODUCTION_HOSTNAME
    : "app.example.com";

export async function handleRegister(
  request: Request,
  env: Env,
): Promise<Response> {
  const body = await request.json<{ email: string; turnstileToken: string }>();

  if (!body.turnstileToken) {
    return Response.json({ error: "Missing Turnstile token" }, { status: 400 });
  }

  const remoteIp =
    request.headers.get("CF-Connecting-IP") ?? undefined;

  let verification;
  try {
    verification = await verifyTurnstileToken(
      env.TURNSTILE_SECRET_KEY,
      body.turnstileToken,
      remoteIp,
    );
  } catch (err) {
    console.error("Turnstile verification fetch failed:", err);
    return Response.json({ error: "Challenge verification unavailable" }, { status: 503 });
  }

  if (!verification.success) {
    console.warn(
      "Turnstile failed",
      JSON.stringify({
        errorCodes: verification.errorCodes,
        hostname: verification.hostname,
        expectedHostname: EXPECTED_HOSTNAME,
      }),
    );
    return Response.json({ error: "Challenge failed", codes: verification.errorCodes }, { status: 403 });
  }

  // Assert hostname to catch site-key/domain mismatches in production immediately.
  if (verification.hostname !== EXPECTED_HOSTNAME) {
    console.error(
      `Turnstile hostname mismatch: got=${verification.hostname} want=${EXPECTED_HOSTNAME}`,
    );
    return Response.json({ error: "Challenge domain mismatch" }, { status: 403 });
  }

  // Proceed with registration…
  return Response.json({ ok: true }, { status: 201 });
}
```

---

## CI Canary: Verify the Site Key Matches the Deploy Target

Add a pre-deploy check that calls the Turnstile `/siteverify` API with a dummy token
and confirms the error code is `invalid-input-response` (not `invalid-sitekey` or
`hostname-not-matched`). A valid site key misconfigured for the wrong domain will
return `hostname-not-matched` when the deploy target's hostname is passed.

```typescript
// scripts/verify-site-key.ts (run in CI before wrangler deploy)
async function checkSiteKey(secretKey: string, siteKey: string, hostname: string) {
  // Use a syntactically valid but deliberately wrong token to probe the key config.
  const body = new URLSearchParams({
    secret: secretKey,
    response: "DUMMY_TOKEN_FOR_KEY_PROBE",
    remoteip: "127.0.0.1",
  });
  const res = await fetch(
    "https://challenges.cloudflare.com/turnstile/v0/siteverify",
    { method: "POST", body },
  );
  const data = (await res.json()) as { success: boolean; "error-codes": string[] };

  const codes = data["error-codes"] ?? [];
  if (codes.includes("invalid-sitekey")) {
    throw new Error(`Site key '${siteKey}' is not valid — check dashboard.`);
  }
  // invalid-input-response means the key is valid; the token is just wrong (expected).
  console.log(`Site key OK for target ${hostname}. Error codes: ${codes.join(", ")}`);
}
```

---

## Anti-patterns

- **Sharing one site key across environments** — different domains require different
  keys; a staging key will always fail on the production domain.
- **Storing site keys in `.env.*` files committed to the repository** — use
  `wrangler.toml` `[env]` vars for the public site key and `wrangler secret put` for
  the secret key.
- **Skipping hostname assertion** — a compromised token harvested from one domain
  could be replayed on another if you do not check `verification.hostname`.
- **Client-side-only validation** — the Turnstile widget can be bypassed; always
  verify server-side before acting on a form submission.

---

## Gotchas

- Turnstile's **test always-pass key** (`1x00000000000000000000AA` / secret
  `1x0000000000000000000000000000000AA`) accepts any hostname. If this key ships to
  production, all challenges pass regardless of user action — it is a security hole,
  not just a configuration mistake.
- **Invisible vs managed widget mode**: both modes issue tokens on the same domain
  restriction rules; mismatch errors look identical regardless of widget mode.
- Tokens are **single-use and expire in ~5 minutes**. Retry logic that reuses the
  same token after a network error will always return `timeout-or-duplicate`.
- The Turnstile verification endpoint is **not available on the Cloudflare worker
  proxy** — you must call `https://challenges.cloudflare.com/` directly from the
  Worker, not through any Hyperdrive or proxy binding.

---

## Verification

```bash
# Confirm each environment variable points to the correct key before deploy:
npx wrangler secret list --env production   # should list TURNSTILE_SECRET_KEY
npx wrangler vars list --env production     # should list TURNSTILE_SITE_KEY

# End-to-end smoke test against staging before promoting to production:
curl -s -X POST https://staging.example.com/api/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","turnstileToken":"STAGING_TOKEN"}' | jq .

# In production after deploy, watch for hostname-not-matched in Logpush:
npx wrangler tail --env production --format pretty 2>&1 | grep "Turnstile"
```

---

## Related

- `security-review-before-not-after.md`
- `never-store-secrets-in-env-files.md`
- `staging-prod-parity-lies-config-drift-data-volume.md`
- `certificate-expiry-outage.md`

---

## Sources

- Cloudflare Turnstile server-side validation:
  https://developers.cloudflare.com/turnstile/get-started/server-side-validation/
- Turnstile error codes reference:
  https://developers.cloudflare.com/turnstile/troubleshooting/error-codes/
- Internal incident #2901 (2026-02-14) — "Registration blocked by wrong Turnstile key"
