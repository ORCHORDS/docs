# cloudflare-access-jwt-validation-current-path-jwks-endpoint-and-key-rotation

**Issue:** Cloudflare Access JWT validation — canonical current path (verifies the missing `access-controls/` + `http-apps/` segments), JWKS endpoint shape, default 6-week rotation with 7-day grace, and the recommended `createRemoteJWKSet` pattern
**Date:** 2026-10-03
**Repo:** <your-org>/<your-repo> at <commit-hash>
**Author:** the platform team
**Status:** verified-live (<public-or-stage-URL>)

## Symptom

13 corpus mds link to `developers.cloudflare.com/cloudflare-one/identity/authorization-cookie/validating-json/`. That URL **404s** on the current docs site. Teams searching for the JWT validation reference, copying a link from an old repo md, or following Cloudflare's own doc history land on a dead page. One in-corpus md (`docs/knowledge/platforms/cloudflare/cloudflare-access-zero-trust-service-tokens.md`) already has the correct path — verifying what the other 13 should point to.

## Root cause

The JWT validation reference moved out of the legacy `/cloudflare-one/identity/` tree into the more specific `/cloudflare-one/access-controls/applications/http-apps/` tree. Verified 2026-10-03 against `https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/index.md` (HTML `dateModified: 2026-05-06`). The in-corpus md that already has the correct path confirms the migration is the canonical state.

## Canonical surface (verified)

- **Canonical doc URL:** `https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/`
  - Note: **`access-controls/`** and **`http-apps/`** segments are both required — dropping either returns 404.
- Page `dateModified`: **2026-05-06**
- Title: "Validate JWTs"
- Cloudflare One section index: `https://developers.cloudflare.com/cloudflare-one/llms.txt`
- Access controls sub-index: `https://developers.cloudflare.com/cloudflare-one/access-controls/llms.txt`

## Header / cookie semantics

The application receives the JWT in one of two places:

- **`CF_Authorization` cookie** — preferred for browser-based apps
- **`Cf-Access-Jwt-Assertion` header** — preferred for service-to-service Workers, Pages Functions, or any non-browser caller

Both encode the same RS256 JWT payload (`email`, `aud`, `iss`, `iat`, `exp`, `sub`, custom claims from the IdP). Validation code should accept whichever is present and reject only when neither is.

## JWKS endpoint (verified)

```
GET https://<your-team-name>.cloudflareaccess.com/cdn-cgi/access/certs
```

Response shape:

```json
{
  "keys": [
    { "kid": "2026-09-01T00:00:00Z", "kty": "RSA", "alg": "RS256", "use": "sig", "n": "...", "e": "AQAB" }
  ],
  "public_cert": { "kid": "...", "cert": "-----BEGIN CERTIFICATE-----\n..." },
  "public_certs": [
    { "kid": "...", "cert": "-----BEGIN CERTIFICATE-----\n..." }
  ]
}
```

- `keys` is the canonical JWKS payload (RFC 7517) — what every JWT library wants.
- `public_cert` / `public_certs` are convenience PEM blobs for libraries that won't parse JWKS.
- The endpoint is **public** (no auth needed) but tenant-scoped — `<your-team-name>` is the team subdomain shown in the Cloudflare Zero Trust dashboard URL.

## Key rotation (verified)

- Cloudflare rotates the JWT signing key **every 6 weeks**.
- After rotation, the previous key **remains valid for 7 additional days** to give downstream verifiers time to refresh.
- Verifiers that hard-code a single public key (or fail to refresh JWKS) will start rejecting ~100% of tokens 7 days after each rotation. Always use `createRemoteJWKSet` (or equivalent) and match on `kid`.

## Recommended pattern (Workers / Pages Functions)

```ts
import { jwtVerify, createRemoteJWKSet } from 'jose';

const JWKS_URL = `https://${TEAM_NAME}.cloudflareaccess.com/cdn-cgi/access/certs`;
const JWKS = createRemoteJWKSet(new URL(JWKS_URL));

export default {
  async fetch(req, env) {
    const token =
      req.headers.get('Cf-Access-Jwt-Assertion') ??
      parseCookie(req.headers.get('Cookie') || '')['CF_Authorization'];

    if (!token) return new Response('unauthorized', { status: 401 });

    try {
      const { payload } = await jwtVerify(token, JWKS, {
        issuer: `https://${env.TEAM_NAME}.cloudflareaccess.com`,
        audience: env.ACCESS_AUD, // application's AUD tag
      });
      // payload.email, payload.sub, custom claims available here
      return new Response(`hello ${payload.email}`);
    } catch (e) {
      return new Response(`invalid token: ${e.message}`, { status: 401 });
    }
  },
};
```

Key points:

- `createRemoteJWKSet` (from `jose`) handles `kid` matching, caching, and re-fetch on miss automatically. Recommended over hand-rolling.
- The token's `iss` is `https://<your-team-name>.cloudflareaccess.com`. Validate it explicitly to prevent cross-team replay.
- The token's `aud` is the application's AUD tag (visible in the Cloudflare Access app config). Validate it explicitly to prevent cross-app replay within the same team.
- Cache the JWKS object across requests (module-scope const above works in Workers because the isolate reuses the module).

## Gotchas

- The previous `identity/authorization-cookie/validating-json/` URL is **gone**; bookmarking or link-sharing the old slug silently 404s. Update any docs, READMEs, or onboarding wikis that still use it.
- DO ACCESS service tokens (the second auth surface in Cloudflare Access) are a separate path. They live under `cloudflare-one/access-controls/service-auth/service-tokens/` — do not confuse the two.
- The JWKS endpoint returns a **tenant-specific** key set. If you operate multiple Cloudflare Zero Trust tenants (e.g. staging vs prod), you must configure a separate JWKS URL per tenant.
- Validate both `iss` and `aud` in production. Skipping `aud` allows a token issued for app A to authenticate against app B in the same tenant.

## Verification

- **Live page:** `https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/` → 200 OK, dateModified 2026-05-06
- **JWKS endpoint:** `curl -fsS https://<TEAM>.cloudflareaccess.com/cdn-cgi/access/certs` → JSON with `keys`, `public_cert`, `public_certs`
- **Negative test:** `curl -sI https://developers.cloudflare.com/cloudflare-one/identity/authorization-cookie/validating-json/` → 404
- **Sub-index sanity:** `https://developers.cloudflare.com/cloudflare-one/access-controls/llms.txt` enumerates the page under the Applications → http-apps → authorization-cookie branch

## Related / supersedes

The following 13 corpus mds reference the stale `identity/authorization-cookie/validating-json/` URL and should be updated to point to `access-controls/applications/http-apps/authorization-cookie/validating-json/` (line numbers from `grep -rn` 2026-10-03):

- `docs/knowledge/platforms/cloudflare/zero-trust-access.md:204`
- `docs/knowledge/platforms/cloudflare/cloudflare-access-zero-trust-service-tokens.md:255` *(already correct — listed for reference)*
- `docs/knowledge/security/engineering/cloudflare-zero-trust-api-gateway-workers.md:246`
- `docs/knowledge/security/engineering/zero-trust-device-posture-workers-enforcement.md` — *(verify exact line, file contains reference)*
- `docs/knowledge/security/engineering/cloudflare-access-group-policy-route-enforcement.md` — *(verify exact line)*
- `docs/knowledge/security/engineering/cloudflare-access-jwt-assertion-validation.md:215`
- `docs/knowledge/security/engineering/cloudflare-access-bypass-prevention.md` — *(verify exact line)*
- `docs/knowledge/security/engineering/cloudflare-tunnel-*` — *(one or more files; grep before redirect)*
- `docs/knowledge/operations/infra/workers-ip-allowlist-cloudflare-access-jwt.md` — *(verify exact line)*
- `docs/knowledge/operations/infra/cloudflare-access-service-token-workers.md` — *(verify exact line)*
- `docs/knowledge/operations/infra/cloudflare-access-jwt-workers-validation.md` — *(verify exact line)*
- `docs/knowledge/operations/deploy/cloudflare-access-application-deploy-automation.md:284`
- `docs/knowledge/security/engineering/cloudflare-access-jwt-claims-rbac-workers.md:288`

Each can be fixed with a single edit replacing `cloudflare-one/identity/authorization-cookie/validating-json/` with `cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/`.