# Managing Workers Routes and DNS Records via the Cloudflare API

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

When a new tenant or feature subdomain is provisioned at runtime, the Worker that handles onboarding needs to register a new Workers route and create the corresponding DNS record without manual dashboard intervention. Doing this idempotently — creating the route only if it does not already exist — prevents duplicate-route errors that cause a 409 from the Cloudflare API.

---

## Context

The Cloudflare REST API exposes `/zones/{zone_id}/workers/routes` for managing Workers routes and `/zones/{zone_id}/dns_records` for DNS records. A Cloudflare API token with `Zone:Edit` and `Workers Routes:Edit` permissions scoped to the target zone is required. Calling these endpoints from inside a Worker keeps the provisioning logic co-located with the application code. The idempotent upsert pattern lists existing routes first, checks for the target pattern, and creates only when absent, making it safe to call on every deployment or tenant signup without accumulating duplicate routes.

---

## Section 1 — wrangler.toml bindings

```toml
# wrangler.toml
name = "orchords-provisioner"
main = "src/provisioner.ts"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]

[vars]
ZONE_ID   = "your_zone_id_here"
ZONE_NAME = "example.com"

# The API token is stored as a secret, not a plain var
# wrangler secret put CF_API_TOKEN
```

---

## Section 2 — Worker implementation

```typescript
// src/provisioner.ts
export interface Env {
  CF_API_TOKEN: string;
  ZONE_ID: string;
  ZONE_NAME: string;
}

const CF_API = "https://api.cloudflare.com/client/v4";

// ── helpers ───────────────────────────────────────────────────────────────────
async function cfFetch(
  env: Env,
  path: string,
  init: RequestInit = {}
): Promise<Response> {
  const url = `${CF_API}${path}`;
  const headers = {
    Authorization: `Bearer ${env.CF_API_TOKEN}`,
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  };
  return fetch(url, { ...init, headers });
}

// ── list existing Workers routes for the zone ─────────────────────────────────
async function listRoutes(
  env: Env
): Promise<Array<{ id: string; pattern: string; script: string }>> {
  const res = await cfFetch(env, `/zones/${env.ZONE_ID}/workers/routes`);
  if (!res.ok) throw new Error(`listRoutes ${res.status}: ${await res.text()}`);
  const { result } = (await res.json()) as {
    result: Array<{ id: string; pattern: string; script: string }>;
  };
  return result ?? [];
}

// ── idempotent route upsert ───────────────────────────────────────────────────
async function upsertRoute(
  env: Env,
  pattern: string,
  scriptName: string
): Promise<{ id: string; created: boolean }> {
  const routes = await listRoutes(env);
  const existing = routes.find((r) => r.pattern === pattern);

  if (existing) {
    console.log(`Route already exists: ${pattern} (id=${existing.id})`);
    return { id: existing.id, created: false };
  }

  const res = await cfFetch(env, `/zones/${env.ZONE_ID}/workers/routes`, {
    method: "POST",
    body: JSON.stringify({ pattern, script: scriptName }),
  });
  if (!res.ok) {
    throw new Error(`upsertRoute POST ${res.status}: ${await res.text()}`);
  }
  const { result } = (await res.json()) as { result: { id: string } };
  console.log(`Created route: ${pattern} (id=${result.id})`);
  return { id: result.id, created: true };
}

// ── idempotent CNAME creation ─────────────────────────────────────────────────
async function upsertCname(
  env: Env,
  subdomain: string,
  target: string
): Promise<{ id: string; created: boolean }> {
  // Check if record exists
  const listRes = await cfFetch(
    env,
    `/zones/${env.ZONE_ID}/dns_records?type=CNAME&name=${subdomain}.${env.ZONE_NAME}`
  );
  if (!listRes.ok) {
    throw new Error(`listDns ${listRes.status}: ${await listRes.text()}`);
  }
  const { result: existing } = (await listRes.json()) as {
    result: Array<{ id: string }>;
  };

  if (existing.length > 0) {
    console.log(`DNS CNAME already exists for ${subdomain}`);
    return { id: existing[0].id, created: false };
  }

  const res = await cfFetch(env, `/zones/${env.ZONE_ID}/dns_records`, {
    method: "POST",
    body: JSON.stringify({
      type: "CNAME",
      name: `${subdomain}.${env.ZONE_NAME}`,
      content: target,
      proxied: true,
      ttl: 1, // Auto TTL for proxied records
    }),
  });
  if (!res.ok) {
    throw new Error(`createDns ${res.status}: ${await res.text()}`);
  }
  const { result } = (await res.json()) as { result: { id: string } };
  return { id: result.id, created: true };
}

// ── main handler ─────────────────────────────────────────────────────────────
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const { subdomain, workerScript } = (await request.json()) as {
      subdomain: string;
      workerScript: string;
    };

    if (!subdomain || !workerScript) {
      return Response.json(
        { error: "subdomain and workerScript are required" },
        { status: 400 }
      );
    }

    // Sanitise subdomain to prevent injection
    if (!/^[a-z0-9-]+$/.test(subdomain)) {
      return Response.json({ error: "Invalid subdomain" }, { status: 400 });
    }

    const pattern = `${subdomain}.${env.ZONE_NAME}/*`;
    const cnameTarget = `${workerScript}.${env.ZONE_NAME.split(".")[0]}.workers.dev`;

    const [route, dns] = await Promise.all([
      upsertRoute(env, pattern, workerScript),
      upsertCname(env, subdomain, cnameTarget),
    ]);

    return Response.json({ route, dns });
  },
};
```

---

## Section 3 — Verification / listing routes

```bash
# List all routes for a zone
curl -sf \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/workers/routes" \
  | jq '.result[] | {id, pattern, script}'

# Trigger a tenant provisioning via the Worker
curl -sf -X POST \
  -H "Content-Type: application/json" \
  -d '{"subdomain":"tenant42","workerScript":"orchords-tenant-api"}' \
  https://provisioner.example.com/ | jq .

# Confirm the DNS record is live
dig +short CNAME tenant42.example.com

# Verify the route is now in the list
curl -sf \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/workers/routes" \
  | jq '.result[] | select(.pattern | startswith("tenant42"))'
```

---

## Anti-patterns

- **Creating routes without checking for duplicates** — The API returns 409 on duplicate patterns; always list first and compare before posting.
- **Using a global API key instead of a scoped token** — A scoped API token limits blast radius; a global key can modify any zone in the account.
- **Setting `proxied: false` on the CNAME** — Workers routes only fire for proxied (orange-cloud) records; an unproxied CNAME bypasses the Worker entirely.
- **Embedding the API token in `wrangler.toml` vars** — Vars are visible in the dashboard and deployment metadata; always use `wrangler secret put` for sensitive values.

---

## Gotchas

- Workers routes use glob patterns (`*.example.com/*`), not regexes; a route for `tenant42.example.com/*` does not match `tenant42.example.com` without the trailing slash wildcard.
- A Custom Domain (`cloudflare_worker_domain`) and a Workers Route for the same hostname conflict — use one or the other, not both.
- The Cloudflare API rate limit for zone-level writes is 1 200 requests per 5 minutes; bulk provisioning must implement a retry-with-backoff strategy.
- DNS propagation for a proxied CNAME is near-instant through Cloudflare's edge, but `dig` from outside Cloudflare's network may show a brief NXDOMAIN until the record replicates.

---

## Verification

```bash
# End-to-end smoke test after provisioning
SUBDOMAIN=tenant42
curl -sf https://${SUBDOMAIN}.example.com/ping
# Expected: 200 OK from the bound Worker

# Confirm TTL and proxied status
curl -sf \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records?name=${SUBDOMAIN}.example.com" \
  | jq '.result[] | {name, type, content, proxied}'
```

---

## Related

- `terraform-cloudflare-workers-d1-iac.md`
- `workers-environment-parity-staging-prod.md`

---

## Sources

- Cloudflare Workers Routes API — https://developers.cloudflare.com/api/operations/worker-routes-list-routes
- Cloudflare DNS Records API — https://developers.cloudflare.com/api/operations/dns-records-for-a-zone-list-dns-records
- Cloudflare API Token Permissions — https://developers.cloudflare.com/fundamentals/api/reference/permissions/
