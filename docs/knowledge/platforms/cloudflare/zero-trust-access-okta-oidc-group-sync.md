# Cloudflare Zero Trust Access with Okta OIDC — Group Sync, Claim Mapping, and Session Policy

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Engineers can authenticate to a Cloudflare Access-protected application via Okta SSO but
are immediately denied despite belonging to the correct Okta group. Alternatively, a user
removed from an Okta group still passes Access policy checks for up to 24 hours. The team
needs deterministic Okta group → Access policy mapping with short revocation latency.

## Context

Cloudflare Zero Trust supports Okta as an OIDC identity provider. Group membership is
surfaced as claims inside the OIDC ID token. Access evaluates those claims at session
creation time, not on every request, making revocation latency a first-class concern.

Two integration paths exist:
- **OIDC (native)** — Okta issues tokens directly; groups come as `groups` claim array.
- **SAML** — attribute statements map groups; generally avoid for new setups (no refresh tokens).

This article covers the OIDC path only.

---

## Okta Application Setup

Create a new Okta "OIDC — Web Application" with:
- **Sign-in redirect URI**: `https://<team>.cloudflareaccess.com/cdn-cgi/access/callback`
- **Sign-out redirect URI**: `https://<team>.cloudflareaccess.com/cdn-cgi/access/logout`
- **Grant types**: Authorization Code + Refresh Token

Enable **Groups claim** in the Okta application's Sign On → OpenID Connect ID Token settings:

```json
{
  "groups": {
    "filter": "starts_with",
    "value": "cf-"
  }
}
```

This filters to only groups prefixed `cf-` to avoid bloating the token when an org has
thousands of Okta groups. Access rejects tokens exceeding the 8 KB header budget.

---

## Adding Okta as an Identity Provider in Zero Trust

```bash
# Via Cloudflare API (idempotent upsert)
curl -s -X POST "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/access/identity_providers" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Okta OIDC",
    "type": "oidc",
    "config": {
      "client_id": "'"${OKTA_CLIENT_ID}"'",
      "client_secret": "'"${OKTA_CLIENT_SECRET}"'",
      "auth_url": "https://'"${OKTA_DOMAIN}"'/oauth2/default/v1/authorize",
      "token_url": "https://'"${OKTA_DOMAIN}"'/oauth2/default/v1/token",
      "certs_url": "https://'"${OKTA_DOMAIN}"'/oauth2/default/v1/keys",
      "scopes": ["openid", "email", "profile", "groups"],
      "claims": ["groups", "email"]
    }
  }'
```

The `claims` array tells Access which fields to index from the ID token. Omitting `groups`
here means group-based policy rules silently never match.

---

## Creating Group-Based Access Policies

Once the IdP is configured and groups sync, create Access groups that reference Okta groups
by their claim value (the Okta group name or ID — confirm in Okta's token preview tool):

```bash
# Create an Access group for "cf-engineers" Okta group
curl -s -X POST "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/access/groups" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Okta Engineers",
    "include": [
      {
        "oidc": {
          "identity_provider_id": "'"${IDP_ID}"'",
          "claim_name": "groups",
          "claim_value": "cf-engineers"
        }
      }
    ]
  }'
```

Reference the Access group in an application policy:

```bash
curl -s -X POST "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/access/apps/${APP_ID}/policies" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Allow Engineers",
    "decision": "allow",
    "precedence": 1,
    "include": [{ "group": { "id": "'"${ACCESS_GROUP_ID}"'" } }]
  }'
```

---

## Validating the JWT in a Downstream Worker

Access injects a signed JWT (`Cf-Access-Jwt-Assertion` header) on every request. Validate
it and extract group claims for fine-grained authz inside the Worker:

```ts
import { importJWK, jwtVerify } from 'jose'; // bundled via npm

const CERTS_URL = `https://${TEAM_DOMAIN}.cloudflareaccess.com/cdn-cgi/access/certs`;

async function getPublicKey(kid: string): Promise<CryptoKey> {
  const res = await fetch(CERTS_URL);
  const { keys } = await res.json<{ keys: JsonWebKey[] }>();
  const jwk = keys.find((k) => k.kid === kid);
  if (!jwk) throw new Error('Unknown kid');
  return importJWK(jwk, 'RS256') as Promise<CryptoKey>;
}

export async function validateAccessJWT(
  token: string
): Promise<{ email: string; groups: string[] }> {
  const header = JSON.parse(atob(token.split('.')[0]));
  const key = await getPublicKey(header.kid);
  const { payload } = await jwtVerify(token, key, {
    issuer: `https://${TEAM_DOMAIN}.cloudflareaccess.com`,
    audience: APP_AUD,
  });
  return {
    email: payload.email as string,
    groups: (payload['custom:groups'] ?? payload.groups ?? []) as string[],
  };
}
```

---

## Reducing Revocation Latency

Access session lifetime defaults to 24 hours. For security-sensitive apps:

1. Set **Application Session Duration** to `30m` in Zero Trust → Access → Applications →
   Configure → Session Duration.
2. Enable **Enable re-authentication on IDP session expiry** — forces re-auth when the
   Okta session ends (Okta default: 2 h).
3. Use **WARP mandatory gateway** posture check to continuously validate device health
   independent of Access session TTL.

For near-real-time revocation (e.g. HR offboarding), use Okta's SCIM provisioning to
Zero Trust — covered in `zero-trust-scim-deprovisioning-and-group-policy.md`.

---

## Anti-patterns

- Using the Okta `id_token` `groups` claim with >50 groups — token bloat causes 431
  header-too-large errors at the Access ingress.
- Matching Okta group by **display name** when the name contains spaces; URL-encode or
  switch to matching by Okta Group ID (stable across renames).
- Setting session duration to `Never` for developer tools; a compromised long-lived
  session has no forced expiry path short of revoking the user's Access token manually.
- Forgetting to add the `offline_access` scope — without it, Access cannot refresh tokens
  and users must re-authenticate every hour regardless of session duration setting.

---

## Gotchas

- Okta's token preview ("Token Preview" in the Okta app's Sign On tab) is the only way
  to confirm which group names actually appear in the `groups` claim before wiring up
  Access policies.
- If the Okta app uses a **custom authorization server** (not `default`), the `certs_url`
  path changes: `.../oauth2/<auth-server-id>/v1/keys`.
- Access caches IdP public keys for 10 minutes; rotating Okta signing keys causes a
  brief auth failure window — stagger key rotation with at least a 15-minute overlap.
- `claims` in the Access IdP config are case-sensitive and must match the Okta claim name
  exactly (`groups`, not `Groups`).

---

## Verification

```bash
# 1. Trigger a test auth and capture the JWT
curl -s "https://your-app.example.com" \
  -H "Cookie: CF_Authorization=<token>" -D - | head -5

# 2. Decode payload (no verification — for debugging only)
echo "<jwt_payload_segment>" | base64 -d | jq '.groups'

# 3. Confirm Access sees the group
# Zero Trust Dashboard → My Team → Users → click user → View auth details
# "groups" should list Okta group values

# 4. Test policy evaluation via Access audit log
# Zero Trust → Logs → Access → filter by email, check "Action: Allow/Block"
```

---

## Related

- `zero-trust-access.md`
- `cloudflare-access-jwt-validation.md`
- `zero-trust-scim-deprovisioning-and-group-policy.md`
- `zero-trust-device-posture.md`
- `cloudflare-access-zero-trust-service-tokens.md`

---

## Sources

- https://developers.cloudflare.com/cloudflare-one/identity/idp-integration/okta/
- https://developers.cloudflare.com/cloudflare-one/policies/access/
- https://developers.cloudflare.com/cloudflare-one/identity/path/to/
- https://developer.okta.com/docs/guides/customize-tokens-returned-from-okta/
