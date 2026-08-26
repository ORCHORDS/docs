# cloudflare-access-jwt-validation

**Issue:** Validating Cloudflare Access JWTs in a Worker or backend service
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cloudflare Access injects a JWT (`Cf-Access-Jwt-Assertion` header) into every authenticated request. Your application must verify this JWT's signature and audience tag to prevent bypass attacks — trusting the header alone is insecure.

## Pattern / Solution

```typescript
import { jwtVerify, createRemoteJWKSet } from 'jose';

const TEAM_DOMAIN = 'https://myteam.cloudflareaccess.com';
const AUD_TAG = 'your-application-audience-tag'; // from Access app settings

// Cache the JWKS fetcher to avoid fetching on every request
let JWKS: ReturnType<typeof createRemoteJWKSet>;

function getJWKS() {
  if (!JWKS) {
    JWKS = createRemoteJWKSet(new URL(`${TEAM_DOMAIN}/cdn-cgi/access/certs`));
  }
  return JWKS;
}

export async function validateAccessJWT(request: Request): Promise<{
  email: string;
  sub: string;
  groups: string[];
} | null> {
  const token = request.headers.get('Cf-Access-Jwt-Assertion');
  if (!token) return null;

  try {
    const { payload } = await jwtVerify(token, getJWKS(), {
      issuer: TEAM_DOMAIN,
      audience: AUD_TAG,
    });

    return {
      email: payload.email as string,
      sub: payload.sub as string,
      groups: (payload['custom_claim_groups'] as string[]) ?? [],
    };
  } catch (err) {
    console.warn('JWT validation failed:', err);
    return null;
  }
}

// Usage in a Worker
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const user = await validateAccessJWT(request);
    if (!user) {
      return new Response('Unauthorized', { status: 401 });
    }

    // Additional group check
    if (!user.groups.includes('engineers')) {
      return new Response('Forbidden', { status: 403 });
    }

    return Response.json({ user });
  },
};
```

**Service token validation (for machine-to-machine):**
```typescript
function validateServiceToken(request: Request, env: Env): boolean {
  const id = request.headers.get('Cf-Access-Client-Id');
  const secret = <redacted-secret>'Cf-Access-Client-Secret');
  return id === env.SERVICE_CLIENT_ID && secret === env.SERVICE_CLIENT_SECRET;
}
```

**Fetching JWKS manually (no external library):**
```bash
curl https://myteam.cloudflareaccess.com/cdn-cgi/access/certs
# Returns { "keys": [...RSA public keys...] }
```

## Gotchas
- Never trust `Cf-Access-Authenticated-User-Email` header alone — it is not signed and can be spoofed.
- The JWKS endpoint caches keys; Cloudflare rotates keys periodically — always fetch JWKS dynamically (use `createRemoteJWKSet`).
- The `aud` claim in the JWT must match your application's **Audience Tag** exactly (found in Access → Applications → your app).
- JWTs expire after **1 hour** by default; users get a new token transparently via the Access login cookie.
- Workers using `jose` need the library bundled — add it: `npm install jose`.
- Service tokens (`Cf-Access-Client-Id` / `Cf-Access-Client-Secret`) are separate from user JWTs and do not have an `email` claim.

## Related
- `zero-trust-access.md`
- `pages-access-integration.md`
- `workers-mtls-certificates.md`
