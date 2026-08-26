# zero-trust-access

**Issue:** Cloudflare Zero Trust Access — protecting internal tools, Worker-to-Worker auth, JWT validation
**Date:** 2026-08-11
**Status:** documented

## Symptom
Your admin panel is exposed to the internet behind only a password.
A Worker needs to call another internal Worker without leaking a
long-lived secret. You get `403` from Access even though the JWT looks
valid.

## Root cause
**Cloudflare Access terminates unauthenticated sessions at the edge.**
Without a properly validated JWT or Service Token, every request to a
protected application is rejected — even requests that originate from
your own Workers.

**Source:** https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/self-hosted-apps/

## Protecting an internal tool with Access

Access sits in front of any hostname you add as a "Self-Hosted
Application." All traffic passes through Cloudflare's global network;
unauthenticated requests never reach your origin Worker.

```toml
# wrangler.toml — no special config needed; Access is configured in the dashboard
# Your Worker is just the origin behind the Access policy
name = "example project-admin"
main = "src/index.ts"
compatibility_date = "2025-01-01"
```

Dashboard path:
Zero Trust → Access → Applications → Add an application → Self-hosted
- Application name: example project-admin
- Session Duration: 24h
- Add a policy: Include → Emails ending in → example.com

## Service Tokens for Worker-to-Worker auth

Use Service Tokens (not user JWTs) when one Worker calls another
protected Worker. The token is a static `CF-Access-Client-Id` /
`CF-Access-Client-Secret` pair issued per service.

```typescript
// env.d.ts
interface Env {
  CF_ACCESS_CLIENT_ID: string;      // secret binding
  CF_ACCESS_CLIENT_SECRET: string;  // secret binding
}

// Calling a protected internal Worker
async function callInternalWorker(
  url: string,
  body: unknown,
  env: Env,
): Promise<Response> {
  return fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "CF-Access-Client-Id": env.CF_ACCESS_CLIENT_ID,
      "CF-Access-Client-Secret": env.CF_ACCESS_CLIENT_SECRET,
    },
    body: JSON.stringify(body),
  });
}
```

Store the credentials as Worker secrets:
```bash
wrangler secret put CF_ACCESS_CLIENT_ID
wrangler secret put CF_ACCESS_CLIENT_SECRET
```

## JWT validation in a Worker (user-facing Access)

When a user authenticates, Access sets a `CF_Authorization` cookie
containing a signed JWT. Validate it in your Worker instead of trusting
the request blindly.

```typescript
import { jwtVerify, createRemoteJWKSet } from "jose";

const JWKS_URL =
  "https://<your-team>.cloudflareaccess.com/cdn-cgi/access/certs";
const JWKS = createRemoteJWKSet(new URL(JWKS_URL));

export async function validateAccessJWT(
  request: Request,
  audience: string,
): Promise<{ email: string; sub: string } | null> {
  const token =
    request.headers.get("Cf-Access-Jwt-Assertion") ??
    getCookie(request, "CF_Authorization");

  if (!token) return null;

  try {
    const { payload } = await jwtVerify(token, JWKS, {
      audience,
      issuer: `https://<your-team>.cloudflareaccess.com`,
    });
    return {
      email: payload.email as string,
      sub: payload.sub as string,
    };
  } catch {
    return null;
  }
}

function getCookie(req: Request, name: string): string | undefined {
  const header = req.headers.get("cookie") ?? "";
  return header
    .split(";")
    .map((c) => c.trim())
    .find((c) => c.startsWith(`${name}=`))
    ?.slice(name.length + 1);
}

// In your handler:
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const user = await validateAccessJWT(
      request,
      env.CF_ACCESS_AUD, // Application Audience tag from Access dashboard
    );
    if (!user) {
      return new Response("Unauthorized", { status: 401 });
    }
    // user.email is verified
    return handleAdminRequest(request, env, user);
  },
};
```

The Audience tag is found in Zero Trust → Access → Applications →
(your app) → Overview → Application Audience.

## Bypassing Access for specific routes

Some routes (webhooks, health checks) must be reachable without
authentication. Use "Bypass" policies scoped to exact paths.

```
Policy name: Bypass health check
Action: Bypass
Include: Everyone
Path: /health
```

Or via the API:
```bash
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/{account_id}/access/apps/{app_id}/policies" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{
    "name": "Bypass health check",
    "decision": "bypass",
    "include": [{"everyone": {}}],
    "exclude": [],
    "require": [],
    "session_duration": "0s",
    "path": "/health"
  }'
```

## Enforcing specific routes (re-auth)

For destructive admin actions, require re-authentication even during an
active session using "Purpose Justification" or re-auth policies:

Dashboard: Policy → Require → Authentication method →
  "Prompt for additional authentication before granting access"

## Verification
- Hit the protected URL in an incognito tab — expect redirect to Access login
- Send a request with valid Service Token headers — expect 200
- Send a request with an expired JWT — expect 401 from your Worker
- `wrangler tail` to confirm JWT validation errors are logged

## Gotchas
- **The "JWKS cached" gotcha.** `createRemoteJWKSet` caches keys. Keys
  rotate every ~6 weeks. jose handles this automatically via HTTP
  cache headers; do not hardcode the public key.
- **The "Audience tag" gotcha.** Each Access Application has its own
  Audience tag. Using the wrong one causes `jwtVerify` to throw even
  with a valid JWT.
- **The "header vs cookie" gotcha.** Browser requests send
  `CF_Authorization` as a cookie. Worker-to-Worker requests using
  `CF-Access-Jwt-Assertion` header. Check both.
- **The "bypass order" gotcha.** Bypass policies must be listed before
  Allow policies in the policy list, otherwise the Allow policy wins.

## Related
- `cloudflare/workers-best-practices.md`
- `security/jwt-best-practices.md`
- `security/oauth-best-practices.md`
- CF Access docs: https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/self-hosted-apps/
- CF Service Tokens: https://developers.cloudflare.com/cloudflare-one/identity/service-tokens/
- CF JWT validation: https://developers.cloudflare.com/cloudflare-one/identity/authorization-cookie/validating-json/
