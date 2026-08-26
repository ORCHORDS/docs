# Protecting Internal Workers with Cloudflare Access Service Tokens

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

An internal Worker that must only be called by other Workers — never by public clients — needs authentication that does not require a shared secret stored in plain-text environment variables. Cloudflare Access service tokens provide a managed credential with a defined expiry and an audit trail, eliminating hand-rolled HMAC schemes between Workers.

---

## Context

Cloudflare Zero Trust issues service tokens as a pair of `CF-Access-Client-Id` / `CF-Access-Client-Secret` headers. An Access policy attached to the internal Worker's hostname enforces that every request carries a valid service token before it reaches the Worker. The calling Worker reads the token from secrets and injects the headers on every outbound request. The receiving Worker can optionally verify the Access JWT signed by the account's public key to obtain identity claims without an extra network call. A Cron Trigger Worker handles token rotation by creating a new token via the Zero Trust API and storing the updated credentials as Worker secrets.

---

## Section 1 — Zero Trust and wrangler.toml configuration

```toml
# wrangler.toml for the CALLING Worker (e.g. orchords-api)
name = "orchords-api"
main = "src/caller.ts"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]

[vars]
INTERNAL_WORKER_URL = "https://internal.example.com"

# Secrets set via:
#   wrangler secret put CF_CLIENT_ID
#   wrangler secret put CF_CLIENT_SECRET
```

```toml
# wrangler.toml for the RECEIVING Worker (e.g. orchords-internal)
name = "orchords-internal"
main = "src/internal.ts"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]

[vars]
# The Access team domain used to fetch the public key
ACCESS_TEAM_DOMAIN = "orchords.cloudflareaccess.com"
# The audience tag from the Access application
ACCESS_AUD         = "your_access_application_aud_tag"
```

---

## Section 2 — Worker implementations

```typescript
// src/caller.ts — the Worker that calls the internal service
export interface Env {
  CF_CLIENT_ID: string;
  CF_CLIENT_SECRET: string;
  INTERNAL_WORKER_URL: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Forward request to the internal Worker with Access service token headers
    const internalUrl = `${env.INTERNAL_WORKER_URL}${new URL(request.url).pathname}`;

    const internalRes = await fetch(internalUrl, {
      method: request.method,
      headers: {
        // Pass through content type and body headers
        ...Object.fromEntries(request.headers),
        // Inject Access service token
        "CF-Access-Client-Id":     env.CF_CLIENT_ID,
        "CF-Access-Client-Secret": env.CF_CLIENT_SECRET,
      },
      body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
    });

    if (!internalRes.ok) {
      console.error(
        `Internal Worker returned ${internalRes.status}: ${await internalRes.text()}`
      );
      return new Response("Internal service error", { status: 502 });
    }

    return internalRes;
  },
};
```

```typescript
// src/internal.ts — the protected Worker that verifies the Access JWT
import type { JwtPayload } from "./types";

export interface Env {
  ACCESS_TEAM_DOMAIN: string;
  ACCESS_AUD: string;
}

// Cache the public keys for the lifetime of the isolate
let cachedKeys: CryptoKey[] | null = null;

async function getAccessPublicKeys(teamDomain: string): Promise<CryptoKey[]> {
  if (cachedKeys) return cachedKeys;

  const certsUrl = `https://${teamDomain}/cdn-cgi/access/certs`;
  const res = await fetch(certsUrl);
  if (!res.ok) throw new Error(`Failed to fetch Access public keys: ${res.status}`);

  const { keys } = (await res.json()) as { keys: JsonWebKey[] };
  cachedKeys = await Promise.all(
    keys.map((jwk) =>
      crypto.subtle.importKey(
        "jwk",
        jwk,
        { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
        false,
        ["verify"]
      )
    )
  );
  return cachedKeys;
}

async function verifyAccessJwt(
  env: Env,
  jwtToken: string
): Promise<JwtPayload> {
  const [headerB64, payloadB64, sigB64] = jwtToken.split(".");
  if (!headerB64 || !payloadB64 || !sigB64) {
    throw new Error("Malformed JWT");
  }

  const encoder = new TextEncoder();
  const data = encoder.encode(`${headerB64}.${payloadB64}`);
  const sig = Uint8Array.from(atob(sigB64.replace(/-/g, "+").replace(/_/g, "/")), (c) =>
    c.charCodeAt(0)
  );

  const keys = await getAccessPublicKeys(env.ACCESS_TEAM_DOMAIN);
  let verified = false;
  for (const key of keys) {
    if (await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, sig, data)) {
      verified = true;
      break;
    }
  }
  if (!verified) throw new Error("JWT signature verification failed");

  const payload = JSON.parse(atob(payloadB64)) as JwtPayload;
  if (payload.aud !== env.ACCESS_AUD) throw new Error("JWT audience mismatch");
  if (payload.exp < Math.floor(Date.now() / 1000)) throw new Error("JWT expired");

  return payload;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const jwtToken = request.headers.get("Cf-Access-Jwt-Assertion");
    if (!jwtToken) {
      return new Response("Missing Access JWT", { status: 401 });
    }

    let identity: JwtPayload;
    try {
      identity = await verifyAccessJwt(env, jwtToken);
    } catch (err) {
      console.error("Access JWT verification failed:", err);
      return new Response("Forbidden", { status: 403 });
    }

    // Identity is verified — proceed with the request
    return Response.json({
      message: "Hello from the internal Worker",
      caller: identity.email ?? identity.sub,
    });
  },
};
```

```typescript
// src/types.ts
export interface JwtPayload {
  aud: string;
  exp: number;
  sub: string;
  email?: string;
  iat: number;
}
```

---

## Section 3 — Token rotation Cron Worker

```typescript
// src/rotator.ts — runs on a schedule to rotate the service token
export interface Env {
  CF_API_TOKEN: string;       // Zero Trust API token with Access:Edit permission
  CF_ACCOUNT_ID: string;
  SERVICE_TOKEN_ID: string;   // ID of the token to rotate
  // Worker secret store: requires Workers for Platforms or direct API update
  CALLER_WORKER_NAME: string;
}

const ZT_API = "https://api.cloudflare.com/client/v4";

async function rotateServiceToken(env: Env): Promise<void> {
  // 1. Create a new service token
  const createRes = await fetch(
    `${ZT_API}/accounts/${env.CF_ACCOUNT_ID}/access/service_tokens`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        name: `orchords-internal-${Date.now()}`,
        duration: "8760h", // 1 year
      }),
    }
  );

  if (!createRes.ok) {
    throw new Error(`Failed to create service token: ${createRes.status}`);
  }

  const {
    result: { client_id, client_secret },
  } = (await createRes.json()) as {
    result: { id: string; client_id: string; client_secret: string };
  };

  // 2. Update secrets on the calling Worker via the Workers API
  await Promise.all([
    putSecret(env, "CF_CLIENT_ID", client_id),
    putSecret(env, "CF_CLIENT_SECRET", client_secret),
  ]);

  console.log("Service token rotated successfully.");

  // 3. Delete the old token (optional — keeps the Access policy clean)
  await fetch(
    `${ZT_API}/accounts/${env.CF_ACCOUNT_ID}/access/service_tokens/${env.SERVICE_TOKEN_ID}`,
    {
      method: "DELETE",
      headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` },
    }
  );
}

async function putSecret(
  env: Env,
  name: string,
  value: string
): Promise<void> {
  const res = await fetch(
    `${ZT_API}/accounts/${env.CF_ACCOUNT_ID}/workers/scripts/${env.CALLER_WORKER_NAME}/secrets`,
    {
      method: "PUT",
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ name, text: value, type: "secret_text" }),
    }
  );
  if (!res.ok) {
    throw new Error(`putSecret(${name}) failed: ${res.status} ${await res.text()}`);
  }
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await rotateServiceToken(env);
  },
};
```

---

## Anti-patterns

- **Checking only the `CF-Access-Client-Id` header and not verifying the JWT** — The `Cf-Access-Jwt-Assertion` header carries the cryptographically signed token; header values alone can be forged if the request bypasses Access.
- **Caching the Access public keys indefinitely across deployments** — Keys rotate; cache them in the isolate scope (per-instance) but always re-fetch on a signature-verification failure to pick up new keys.
- **Storing `CF_CLIENT_SECRET` in `wrangler.toml` `[vars]`** — Vars are visible in deployment metadata; use `wrangler secret put` or the rotator Worker's `putSecret` call.
- **Not scoping the API token used by the rotator** — The rotation token needs only `Access:Edit` and `Workers Scripts:Edit` for the specific account; a global token is overpowered.

---

## Gotchas

- `Cf-Access-Jwt-Assertion` is injected by Cloudflare's edge only when the request passes through an Access policy; it is absent on direct-to-Worker calls that bypass the domain (e.g., `workers.dev` URLs).
- Service tokens created via the API default to expiry after 1 year; set a calendar reminder or automate rotation before the expiry date to prevent silent auth failures.
- The public key endpoint (`/cdn-cgi/access/certs`) returns keys in JWKS format; each key has a `kid` claim that matches the JWT header's `kid` — matching by `kid` before attempting verification is more efficient than trying all keys.
- Updating Worker secrets via the API does not trigger a new Worker deployment; the secret value is updated in-place and takes effect on the next isolate cold-start.

---

## Verification

```bash
# Verify the Access policy is enforced (should return 403 without token)
curl -sf https://internal.example.com/ping
# Expected: 403 Forbidden from Access

# Call with a valid service token (simulates the calling Worker)
curl -sf https://internal.example.com/ping \
  -H "CF-Access-Client-Id: ${CF_CLIENT_ID}" \
  -H "CF-Access-Client-Secret: ${CF_CLIENT_SECRET}" \
  | jq .
# Expected: 200 with caller identity

# List existing service tokens for the account
curl -sf \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/access/service_tokens" \
  | jq '.result[] | {id, name, expires_at}'
```

---

## Related

- `workers-multi-region-failover-d1.md`
- `workers-environment-parity-staging-prod.md`

---

## Sources

- Cloudflare Access Service Tokens — https://developers.cloudflare.com/cloudflare-one/identity/service-tokens/
- Cloudflare Access JWT Verification — https://developers.cloudflare.com/cloudflare-one/identity/authorization-cookie/validating-json/
- Workers Secrets API — https://developers.cloudflare.com/api/operations/worker-secrets-list-secrets
