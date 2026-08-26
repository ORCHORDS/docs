# Workers Smart Placement and Data Residency Compliance

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
You enable Cloudflare Workers Smart Placement to reduce latency and then discover that GDPR, DPDP, or contractual data-residency obligations require processing to remain within a specific geographic region — but Smart Placement has moved invocations outside that region.

## Context
Smart Placement analyses routing costs and moves your Worker invocation closer to the backend data source (a D1 database, Hyperdrive endpoint, or origin API). When the backend is in `us-east-1`, Cloudflare may transparently execute the Worker in a North American PoP even if the request originated in the EU. For most applications this is desirable, but it breaks GDPR Article 46 transfer safeguards if personal data is processed outside the EEA without a valid legal mechanism. Cloudflare exposes Regional Hints (`cf.region` binding and the `--placement` wrangler setting) and Data Localisation Suite (DLS) features to enforce geographic constraints while retaining some of Smart Placement's latency benefits.

## Understanding What Smart Placement Moves
Smart Placement relocates the Worker's compute, not the data. It does not copy D1 rows or KV values to the closer PoP; it moves the CPU execution of your Worker code. Any personal data that the Worker reads from the request body, constructs, or transforms is processed at the new PoP location.

```typescript
// Inspect the actual execution location at runtime for auditing
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const colo = (request.cf as CfProperties & { colo?: string })?.colo ?? "unknown";
    const country = (request.cf as CfProperties & { country?: string })?.country ?? "unknown";

    // Log to audit trail — does execution location match policy?
    console.log(JSON.stringify({
      event: "request_processed",
      colo,
      country,
      path: new URL(request.url).pathname,
      ts: Date.now(),
    }));

    return handleRequest(request, env);
  },
};
```

## Restricting Execution to an EEA Region
Disable Smart Placement for Workers that handle personal data and instead pin execution to the EU using the `placement` field in `wrangler.toml`.

```toml
# wrangler.toml — EU-resident personal-data handler
name = "eu-personal-data-worker"
compatibility_date = "2026-08-01"

[placement]
mode = "off"

# Cloudflare Data Localisation Suite: restrict to EU PoPs
# Requires Enterprise plan with DLS add-on
[env.production.placement]
mode = "smart"
hint = "EU"
```

```typescript
// Enforce at runtime as a defence-in-depth check
const EU_COUNTRIES = new Set([
  "AT","BE","BG","HR","CY","CZ","DK","EE","FI","FR",
  "DE","GR","HU","IE","IT","LV","LT","LU","MT","NL",
  "PL","PT","RO","SK","SI","ES","SE",
  // EEA additions
  "IS","LI","NO",
]);

async function assertEEAExecution(request: Request): Promise<void> {
  const cf = request.cf as CfProperties & { country?: string };
  const country = cf?.country ?? "";
  if (country && !EU_COUNTRIES.has(country)) {
    // Log anomaly — do not leak internal config to the client
    console.error(JSON.stringify({
      event: "DATA_RESIDENCY_VIOLATION",
      colo: (cf as { colo?: string }).colo,
      country,
    }));
    throw new Error("Execution location policy violation");
  }
}
```

## Separating Personal Data Handlers from Smart-Placed Workers
Split your application into two Worker services: a globally Smart-Placed routing Worker that handles non-personal requests, and a region-locked Worker that processes personal data. Use service bindings to delegate only the personal-data paths.

```typescript
// global-router/src/index.ts — Smart Placement ENABLED
export interface Env {
  EU_PERSONAL_DATA_WORKER: Fetcher; // service binding to the EU-locked worker
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Routes that touch personal data are delegated to the EU worker
    if (url.pathname.startsWith("/api/users") || url.pathname.startsWith("/api/gdpr")) {
      return env.EU_PERSONAL_DATA_WORKER.fetch(request);
    }

    // All other routes run in the globally optimised worker
    return handlePublicRequest(request);
  },
};

async function handlePublicRequest(request: Request): Promise<Response> {
  return new Response("OK", { status: 200 });
}
```

```typescript
// eu-personal-data-worker/src/index.ts — Smart Placement DISABLED
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    try {
      await assertEEAExecution(request);
    } catch {
      return new Response("Service Unavailable", { status: 503 });
    }
    return handlePersonalData(request, env);
  },
};
```

## Audit Logging Execution Location for Compliance Evidence
Maintain an audit log of every request that processes personal data, including the PoP location, for regulatory evidence. Write to D1 (also EU-resident when using DLS).

```typescript
async function logPersonalDataAccess(
  request: Request,
  userId: string,
  action: string,
  env: Env & { AUDIT_DB: D1Database }
): Promise<void> {
  const cf = request.cf as CfProperties & { colo?: string; country?: string };
  await env.AUDIT_DB
    .prepare(`
      INSERT INTO audit_log (user_id, action, colo, country, ip_hash, ts)
      VALUES (?, ?, ?, ?, ?, unixepoch())
    `)
    .bind(
      userId,
      action,
      cf?.colo ?? null,
      cf?.country ?? null,
      await hashIp(request.headers.get("cf-connecting-ip") ?? "")
    )
    .run();
}

async function hashIp(ip: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(ip + "audit-salt-v1")
  );
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

interface Env {}
```

## Anti-patterns
- Enabling Smart Placement globally and assuming data stays in the region where the user's request originated
- Using the requester's IP country as a proxy for the Worker's execution country — they are independent values
- Relying solely on `wrangler.toml` placement hints without a runtime guard, since configuration can be overridden by deployment errors
- Processing personal data in a Smart-Placed Worker that calls an EU-resident database — the data traverses the network from a non-EU PoP to the EU database, creating a Chapter V transfer
- Treating Cloudflare PoP country as a guaranteed legal jurisdiction without validating it against your DPA's data transfer framework

## Gotchas
- `request.cf?.country` reflects the country of the PoP executing the Worker, not the country of the client
- The `placement = { mode = "smart", hint = "EU" }` hint requires the Enterprise Data Localisation Suite add-on — without it the hint is silently ignored
- Service bindings between Workers with different placement modes execute the callee in its own placement context, not the caller's
- D1 databases are single-region by default; verify your D1 database's home region in the dashboard before using it for EEA-resident data
- Smart Placement only activates when Cloudflare's algorithm determines it saves meaningful latency; at low traffic it may not activate at all

## Verification
1. Deploy the EU-locked Worker with `mode = "off"` and inspect `request.cf.colo` in logs from an EU client — confirm the PoP is in an EEA country.
2. Simulate a non-EU invocation by temporarily removing placement restrictions and compare log output.
3. Use Cloudflare's Logpush to export `ClientColo` fields and cross-reference against a list of EU PoPs from the Cloudflare network map.
4. Run a penetration test from a non-EU IP and verify the `assertEEAExecution` guard returns `503`.

## Related
- [Multi-Tenancy Isolation Workers KV D1](multi-tenancy-isolation-workers-kv-d1.md)
- [Service Binding Zero Trust Workers](service-binding-zero-trust-workers.md)
- [Audit Log Security](audit-log-security.md)
- [Workers Service Bindings RPC Security](workers-service-bindings-rpc-security.md)

## Sources
- https://developers.cloudflare.com/workers/configuration/smart-placement/
- https://developers.cloudflare.com/data-localization/
- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- https://gdpr.eu/article-46-gdpr/
- https://www.cloudflare.com/network/
