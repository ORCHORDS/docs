# pages-access-integration

**Issue:** Protecting a Cloudflare Pages site with Cloudflare Access (Zero Trust)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cloudflare Access can gate an entire Pages project or specific paths behind identity verification (SSO, OTP, GitHub, etc.) without adding auth code to the application itself.

## Pattern / Solution

**Dashboard setup:**
1. Zero Trust → Access → Applications → Add Application → **Self-hosted**.
2. Application domain: `my-site.pages.dev` (or your custom domain).
3. Policies: define who can access (email domain, GitHub org, etc.).
4. Save — Access now sits in front of the Pages site.

**Protecting only a path (e.g. `/admin`):**
- Application domain: `my-site.pages.dev`
- Path: `/admin`
- A separate public policy can allow `/*` without auth.

**Reading the Access JWT in a Pages Function:**
```typescript
// functions/api/[[route]].ts
import { jwtVerify, createRemoteJWKSet } from 'jose';

const CERTS_URL = `https://<YOUR_TEAM>.cloudflareaccess.com/cdn-cgi/access/certs`;
const AUDIENCE = '<YOUR_APP_AUD_TAG>';  // from Access application settings

export async function onRequest(ctx: EventContext<Env, string, Record<string, unknown>>) {
  const token = ctx.request.headers.get('Cf-Access-Jwt-Assertion');
  if (!token) return new Response('Missing token', { status: 401 });

  try {
    const JWKS = createRemoteJWKSet(new URL(CERTS_URL));
    const { payload } = await jwtVerify(token, JWKS, { audience: AUDIENCE });
    // payload.email is the authenticated user's email
    ctx.data.user = { email: payload.email as string };
  } catch {
    return new Response('Invalid token', { status: 403 });
  }

  return ctx.next();
}
```

**Bypassing Access for specific paths (service tokens):**
```
# In Access policy, add a "Service Auth" rule for /api/webhook
# The upstream sends the service token header:
Cf-Access-Client-Id: <client-id>
Cf-Access-Client-Secret: <client-secret>
```

## Gotchas
- Access adds `Cf-Access-Jwt-Assertion` and `Cf-Access-Authenticated-User-Email` headers to every request.
- Do not trust `Cf-Access-Authenticated-User-Email` alone — always verify the JWT signature.
- JWKS endpoint caches public keys; call it once per isolate lifecycle, not per request.
- Pages preview deployments (branch URLs) are **not** automatically covered by the production Access policy — add them separately or use a wildcard.
- Access does not protect direct R2/KV data — it only gates the Pages HTTP surface.
- The AUD (audience) tag is per-application — use the correct one for each Access app.

## Related
- `cloudflare-access-jwt-validation.md`
- `zero-trust-access.md`
- `pages-best-practices.md`
