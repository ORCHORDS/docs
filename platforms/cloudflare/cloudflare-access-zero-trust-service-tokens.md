# Cloudflare Access: Zero Trust Service Tokens

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Internal Workers (Queue consumers, cron jobs, webhook handlers)
call admin API endpoints that are fronted by Cloudflare Access.
Requests fail with 403 because they carry no user session.
Human SSO flows are not applicable for machine-to-machine
calls; a credential scheme that rotates safely without
downtime is required.

## Context

WAM (example.com) exposes admin-only endpoints — age-gate
enforcement, bulk content moderation, user-flag ingestion —
behind Cloudflare Access Applications. Background Workers
and third-party pipeline integrations (Pipelines → R2)
must authenticate as "services," not as users. Service
tokens provide a stable, rotatable credential pair that
Access validates at the edge before any request reaches
application code.

## 1. Creating a Service Token

Navigate: **Zero Trust → Access controls → Service
credentials → Service Tokens → Create Service Token**.

1. Enter a descriptive name (e.g. `wam-moderation-worker`).
2. Choose a token duration (recommended: 1 year; set a
   calendar alert one week before expiry).
3. Copy the **Client ID** and **Client Secret** immediately —
   the Secret is shown only once. Loss requires rotating.

Attach the token to an Access Application by adding a
service token policy rule:

```
Policy name : allow-wam-moderation-worker
Action      : Allow
Include     : Service Token = wam-moderation-worker
```

Every request from that Worker must supply both headers:

```
CF-Access-Client-Id: <CLIENT_ID>
CF-Access-Client-Secret: <CLIENT_SECRET>
```

Store the values as Cloudflare Worker secrets:

```bash
wrangler secret put CF_ACCESS_CLIENT_ID
wrangler secret put CF_ACCESS_CLIENT_SECRET
```

Then attach them in `wrangler.toml`:

```toml
[vars]
# non-secret reference; actual values via `wrangler secret`

[[bindings]]  # secrets appear automatically in env
```

Emit them on outbound requests:

```typescript
const resp = await fetch(ADMIN_API_URL, {
  headers: {
    "CF-Access-Client-Id":     env.CF_ACCESS_CLIENT_ID,
    "CF-Access-Client-Secret": env.CF_ACCESS_CLIENT_SECRET,
    "Content-Type":            "application/json",
  },
});
```

## 2. Validating the Access JWT in a Worker

When Access is in front of a Worker, Cloudflare injects a
signed JWT into the `Cf-Access-Jwt-Assertion` header on every
authenticated request. Trusting that header alone is
insufficient — a compromised upstream could forge it. The
Worker must verify the JWT's signature against the JWKS
endpoint for the team domain.

```typescript
import { jwtVerify, createRemoteJWKSet } from "jose";

const TEAM_DOMAIN = "https://wam.cloudflareaccess.com";
const AUD_TAG     = "<APPLICATION_AUD_TAG>"; // from Access app

let jwks: ReturnType<typeof createRemoteJWKSet> | null = null;

function getJWKS() {
  if (!jwks) {
    jwks = createRemoteJWKSet(
      new URL(`${TEAM_DOMAIN}/cdn-cgi/access/certs`),
    );
  }
  return jwks;
}

export async function validateAccessJWT(
  request: Request,
): Promise<{ email: string; sub: string }> {
  const token =
    request.headers.get("Cf-Access-Jwt-Assertion") ?? "";

  const { payload } = await jwtVerify(token, getJWKS(), {
    issuer:   TEAM_DOMAIN,
    audience: AUD_TAG,
  });

  return {
    email: payload.email as string,
    sub:   payload.sub   as string,
  };
}
```

The JWKS endpoint (`/cdn-cgi/access/certs`) returns both
current and previous keys — rotate your code against key IDs
(`kid`) rather than caching a single public key. Cloudflare
rotates the signing key every 6 weeks; the previous key
remains valid for 7 days post-rotation to allow graceful
roll-over.

Use `Cf-Access-Jwt-Assertion` (header), not the
`CF_Authorization` cookie; cookies are not guaranteed to
forward in service-to-service calls.

## 3. Service Token Rotation Procedure

Zero-downtime rotation follows a "create-migrate-delete"
pattern:

```
1. Create a NEW service token (new Client ID + Secret).
2. Update the Access Application policy to include BOTH
   the old and new service tokens.
3. Deploy the updated secret values to every caller
   Worker:
       wrangler secret put CF_ACCESS_CLIENT_ID   (new value)
       wrangler secret put CF_ACCESS_CLIENT_SECRET (new value)
4. Verify callers are authenticated with the new token
   (check Access audit logs — see §5).
5. Remove the OLD service token from the Access policy.
6. Delete the old service token from the dashboard.
```

Do not delete the old token before all callers have migrated.
A gap of even one second causes 403s in production.

## 4. Service Tokens vs mTLS for M2M Auth

| Dimension          | Service Token                  | mTLS Certificate               |
|--------------------|--------------------------------|--------------------------------|
| Credential type    | ID + Secret header pair        | X.509 client certificate       |
| Transport binding  | None (headers only)            | TLS handshake — bound to TLS   |
| Revocation speed   | Instant (delete token)         | CRL/OCSP propagation delay     |
| Setup complexity   | Low                            | High (PKI, cert issuance)      |
| Rotation effort    | Create-migrate-delete (§3)     | Reissue cert, update all callers|
| Replay risk        | Header can be captured/replayed| Certificate tied to private key|
| Best for           | Worker-to-Worker, 3rd-party    | High-security infra, zero-trust|

WAM uses service tokens for Worker-to-Worker and pipeline
integrations. mTLS (Workers mTLS Certificates) is reserved
for external vendors that require transport-layer binding.

## 5. API Shield and Audit Logs

**API-only Access Applications:** Set the application type
to "Self-hosted" and add a "Block" policy with the condition
"Not - Service Token" to reject all browser/human traffic.
This makes the endpoint machine-only without writing any
Worker code.

**Access Audit Logs:** Zero Trust → Logs → Access provides
a real-time view of every authentication event. Filter by
service token name to trace which Worker is calling which
endpoint. Logs are also exportable via Logpush to R2 for
long-term retention.

```bash
# Pull recent Access events via the API
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/${ACCT}/\
access/logs/access-requests?limit=25" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '.result[] | {action, app_name, service_token_id}'
```

Correlate `service_token_id` values against the list
returned by the service tokens API to identify which
credential triggered each event.

## Anti-patterns

- Committing the Client Secret to source control or
  `wrangler.toml` vars — use `wrangler secret put` only.
- Using a single shared service token for every Worker;
  prefer one token per service so audit logs are traceable
  and revocation is surgical.
- Caching the full JWKS response body instead of using
  `createRemoteJWKSet` — the helper handles key-ID matching
  and fetches the latest certs automatically.
- Skipping JWT validation and trusting only the presence
  of `Cf-Access-Jwt-Assertion` — any upstream can set
  that header without Access in the path.

## Gotchas

- The Client Secret is shown exactly once at creation.
  Losing it means creating a brand-new token and rotating
  all callers — there is no "reveal" function.
- Access signing keys rotate every 6 weeks. Hard-coded
  public keys break silently after rotation. Always use
  the JWKS endpoint.
- Service tokens added to an Access Application policy
  take up to 60 seconds to propagate to the edge.
- Token expiry does not block existing in-flight requests;
  the next request after expiry will 403.
- The `CF_Authorization` cookie is set only for browser
  flows. Server-to-server calls must read the header.

## Verification

1. Create a test token; make a curl call with the headers:
   `curl -H "CF-Access-Client-Id: ..." \`
   `-H "CF-Access-Client-Secret: ..." https://admin.example.com/ping`
2. Confirm 200 in the response and the event in Access Logs.
3. Remove the token from the policy; repeat curl — expect 403.
4. In Workers, log `payload.email` from JWT validation to
   confirm the service account identity propagates correctly.
5. Set a dashboard Notification (Access — Service Token
   Expiration) to alert one week before token expiry.

## Related

- `cloudflare-access-jwt-validation.md` — JWT validation
  implementation details
- `zero-trust-access.md` — Access Application setup overview
- `workers-mtls-certificates.md` — mTLS for higher-trust M2M
- `api-token-least-privilege-and-rotation-governance.md`
- `workers-logpush.md` — exporting Access logs to R2

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/
- https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/
- https://developers.cloudflare.com/api-shield/security/jwt-validation/
- https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/service_tokens/
