# Cloudflare for SaaS — Custom Hostnames and SSL for SaaS

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You operate a SaaS platform and want to let each customer use their own branded domain
(e.g. `app.customer.com`) instead of your subdomain (`customer.yoursaas.com`).  Each
customer points their DNS at your infrastructure, but their traffic must still flow through
Cloudflare so you get WAF, caching, and DDoS protection.  You need to provision TLS
certificates for each customer's domain automatically, without requiring them to join your
Cloudflare account.

This is the **Cloudflare for SaaS** (formerly "SSL for SaaS") feature set.

## Context

Cloudflare for SaaS lets a Cloudflare zone act as a **SaaS provider zone** that issues TLS
certificates for **custom hostnames** — domains owned by your customers that resolve to
your Cloudflare zone.

Key concepts:

- **Fallback origin** — the origin IP/hostname that receives traffic for all custom
  hostnames (your load balancer or Workers route).
- **Custom hostname** — a customer's domain (`app.customer.com`) registered in your SaaS
  zone; Cloudflare handles its TLS.
- **Certificate types** — Cloudflare-managed (auto-renewed DV), BYO CA (customer provides
  their own cert), or BYO root CA.
- **Wildcard custom hostnames** — `*.customer.com` support for customers with many
  subdomains.
- **Ownership verification** — before issuing a certificate, Cloudflare verifies the
  customer controls the domain via a CNAME or TXT record.
- **Plans** — Cloudflare for SaaS requires an **Enterprise** plan *or* purchasing the
  SSL for SaaS add-on on Pro/Business.  First 100 custom hostnames are free; $0.10/month
  per additional hostname.

## Section 1 — Zone Setup (Provider Side)

### 1.1 Enable SSL for SaaS on your zone

Dashboard → SSL/TLS → Custom Hostnames → Enable SSL for SaaS

Or via API:

```bash
curl -X POST \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/custom_hostnames/fallback_origin" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"origin": "fallback.yoursaas.com"}'
```

The fallback origin must:
- Have a DNS record in **your** zone (an A/AAAA or CNAME pointing to your servers).
- Be reachable over HTTPS with a valid certificate (either Cloudflare-issued for your zone
  or your own cert on the origin).

### 1.2 Terraform: zone-level fallback origin

```hcl
resource "cloudflare_custom_hostname_fallback_origin" "saas_fallback" {
  zone_id = var.zone_id
  origin  = "fallback.yoursaas.com"
}
```

## Section 2 — Provisioning Custom Hostnames (Customer Onboarding)

When a customer completes onboarding and provides their custom domain:

### 2.1 REST API call (automate from your backend)

```typescript
// Called from your Node.js onboarding backend
async function provisionCustomHostname(
  customerDomain: string,
  zoneId: string,
  apiToken: string
): Promise<{ validationRecords: ValidationRecord[]; hostnameId: string }> {
  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${zoneId}/custom_hostnames`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        hostname: customerDomain,
        ssl: {
          method: "txt",      // TXT record ownership validation
          type: "dv",         // Domain Validated certificate
          settings: {
            min_tls_version: "1.2",
            http2: "on",
            early_hints: "on",
          },
          wildcard: false,    // set true for *.customer.com
          certificate_authority: "lets_encrypt",
        },
      }),
    }
  );

  const data = await resp.json() as CustomHostnameResponse;

  if (!data.success) {
    throw new Error(`Failed to create custom hostname: ${JSON.stringify(data.errors)}`);
  }

  // Return the DNS records the customer must add
  return {
    hostnameId: data.result.id,
    validationRecords: data.result.ssl.validation_records ?? [],
  };
}

interface ValidationRecord {
  txt_name: string;
  txt_value: string;
}

interface CustomHostnameResponse {
  success: boolean;
  errors: Array<{ message: string }>;
  result: {
    id: string;
    ssl: {
      validation_records?: ValidationRecord[];
      status: string;
    };
  };
}
```

### 2.2 What to give the customer

After calling the API, send the customer:

1. **CNAME record** — they add this to their DNS:
   ```
   app.customer.com  CNAME  yoursaas.com
   ```
   (pointing at your zone's apex or a designated hostname)

2. **TXT ownership record** — Cloudflare returns this in `ssl.validation_records`:
   ```
   _cf-custom-hostname.app.customer.com  TXT  "verify-abc123..."
   ```

Both records must propagate before Cloudflare issues the certificate.

### 2.3 Poll for certificate issuance

```typescript
async function pollCertificateStatus(
  hostnameId: string,
  zoneId: string,
  apiToken: string,
  maxWaitMs = 300_000
): Promise<"active" | "failed"> {
  const start = Date.now();

  while (Date.now() - start < maxWaitMs) {
    const resp = await fetch(
      `https://api.cloudflare.com/client/v4/zones/${zoneId}/custom_hostnames/${hostnameId}`,
      { headers: { Authorization: `Bearer ${apiToken}` } }
    );
    const data = await resp.json() as { result: { ssl: { status: string }; status: string } };

    const sslStatus = data.result.ssl.status;
    const hostnameStatus = data.result.status;

    if (sslStatus === "active" && hostnameStatus === "active") {
      return "active";
    }
    if (sslStatus === "pending_deployment" || sslStatus === "pending_validation") {
      await new Promise(r => setTimeout(r, 5000));
      continue;
    }
    // Unexpected status — bail
    console.error("SSL status:", sslStatus, "Hostname status:", hostnameStatus);
    return "failed";
  }
  return "failed";
}
```

Typical issuance time after DNS propagates: 30 seconds – 5 minutes.

## Section 3 — Routing Customer Traffic to Tenant Backends

Once traffic arrives at your zone under a custom hostname, you need to route it to the
correct tenant backend.  A Worker is ideal for this:

```toml
# wrangler.toml
name               = "saas-router"
main               = "src/router.ts"
compatibility_date = "2024-09-23"

[[kv_namespaces]]
binding = "HOSTNAME_MAP"
id      = "abc123..."

[[d1_databases]]
binding      = "DB"
database_id  = "def456..."
database_name = "saas_db"
```

```typescript
// src/router.ts
interface Env {
  HOSTNAME_MAP: KVNamespace;   // hostname → tenant JSON
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const host = request.headers.get("Host") ?? "";

    // Look up tenant config for this custom hostname
    // KV gives ~1 ms lookup; D1 fallback for freshness
    let tenant = await env.HOSTNAME_MAP.get<TenantConfig>(host, "json");

    if (!tenant) {
      // Slower path: DB lookup + cache in KV for 5 minutes
      tenant = await lookupFromDB(host, env.DB);
      if (tenant) {
        ctx.waitUntil(
          env.HOSTNAME_MAP.put(host, JSON.stringify(tenant), { expirationTtl: 300 })
        );
      }
    }

    if (!tenant) {
      return new Response("Unknown hostname", { status: 404 });
    }

    // Forward to tenant origin, preserving the custom hostname
    const targetUrl = new URL(request.url);
    targetUrl.hostname = tenant.origin;

    const originRequest = new Request(targetUrl.toString(), {
      method: request.method,
      headers: request.headers,
      body: request.method !== "GET" && request.method !== "HEAD" ? request.body : undefined,
    });

    // Add tenant identity header for the origin
    originRequest.headers.set("X-Tenant-ID", tenant.id);
    originRequest.headers.set("X-Custom-Hostname", host);

    return fetch(originRequest);
  },
};

interface TenantConfig {
  id: string;
  origin: string;       // e.g. "tenant-abc.internal.yoursaas.com"
  plan: string;
}

async function lookupFromDB(hostname: string, db: D1Database): Promise<TenantConfig | null> {
  const row = await db
    .prepare("SELECT id, origin, plan FROM tenants WHERE custom_hostname = ? LIMIT 1")
    .bind(hostname)
    .first<TenantConfig>();
  return row ?? null;
}
```

## Section 4 — Wildcard Custom Hostnames

For customers who want `*.customer.com` (every subdomain served through your platform):

```bash
curl -X POST \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/custom_hostnames" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "hostname": "*.customer.com",
    "ssl": {
      "method": "txt",
      "type": "dv",
      "wildcard": true,
      "certificate_authority": "lets_encrypt"
    }
  }'
```

The customer adds the same CNAME and TXT records.  Cloudflare issues a wildcard DV cert
covering all subdomains.

**Gotcha**: wildcard custom hostnames require the customer's DNS provider to support CNAME
at the apex (`customer.com CNAME yoursaas.com`) if they want the root domain covered too.
Most providers do not support this (CNAME flattening aside).  Handle apex separately as a
second non-wildcard custom hostname entry.

## Mobile vs Desktop Considerations

- **TLS certificate issuance and iOS Safari** — iOS Safari enforces certificate transparency
  logs.  Let's Encrypt certificates issued through Cloudflare for SaaS are automatically
  submitted to CT logs; no action required.
- **HTTP/2 and HTTP/3** — enable both in the SSL settings (`http2: "on"`, `http3: "on"`).
  Mobile clients on iOS and Android heavily use HTTP/2 multiplexing; HTTP/3/QUIC reduces
  head-of-line blocking on mobile radios.
- **Custom hostname caching** — Cloudflare caches under the custom hostname's zone context.
  If a customer's mobile app sends `Accept: image/webp` but your cache key does not include
  `Accept`, mobile and desktop clients get the same cached response.  Use Cache Rules on
  your zone to `Vary` by `Accept` for image paths.
- **Device type in Worker routing** — `request.cf.deviceType` is still populated for
  custom hostname traffic.  Your SaaS router can pass `X-Device-Type` to the tenant
  origin so multi-tenant backends can return mobile-optimized content.

## Anti-patterns

- **Polling certificate status in a Worker's request path** — polling is asynchronous work
  that belongs in a backend job or Cloudflare Queue consumer, not inline during a web
  request.  Store issuance status in your DB and show the customer a "pending" state in
  your UI.
- **Not deleting custom hostnames when a tenant offboards** — stale hostnames consume quota
  and their certificates continue to renew until deleted.  Implement a `DELETE
  /custom_hostnames/{id}` call in your offboarding flow.
- **Using the same Cloudflare API token for customer-facing webhook responses** — your
  provisioning token has broad zone write access.  Store it in Secrets Store, not in a
  database column the customer can read.
- **Omitting `X-Forwarded-For` / `CF-Connecting-IP` forwarding to origins** — without
  forwarding these headers your origin sees Cloudflare's IP for every tenant request,
  breaking per-tenant IP-based analytics and rate limiting.

## Gotchas

- **Custom hostname status vs SSL status** — both must be `active`.  A hostname can be
  `active` (CNAME verified) but have `ssl.status = "pending_validation"` (TXT not yet
  propagated).  Check both fields.
- **Hostname conflicts** — if a customer's domain is also proxied through their own
  Cloudflare account, the custom hostname provisioning will fail with a conflict.  The
  customer must either remove their domain from their own Cloudflare account or use DNS-only
  (orange-clouded off) mode.
- **Certificate renewal** — Cloudflare renews DV certs automatically ~30 days before
  expiry.  Renewal requires the CNAME to still be in place.  If a customer removes their
  CNAME (e.g., they migrated away), their cert expires silently.  Monitor via the
  `custom_hostname.certificate.expired` Cloudflare notification.
- **Rate limits on the Custom Hostnames API** — creating custom hostnames is rate-limited
  to ~10 per second per zone.  For bulk onboarding (>1000 tenants), spread calls across
  multiple seconds or batch with a queue.
- **Fallback origin must be in the SaaS provider zone** — you cannot set an external IP
  directly as the fallback origin; it must be a hostname with a DNS record in your zone.

## Verification

```bash
# 1. List custom hostnames and check status
curl -s \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/custom_hostnames?per_page=20" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | \
  jq '.result[] | {hostname, status, ssl_status: .ssl.status}'

# 2. Test a specific custom hostname
curl -sv --resolve "app.customer.com:443:$(dig +short yoursaas.com)" \
  https://app.customer.com/health

# 3. Verify the certificate is for the custom hostname
echo | openssl s_client -connect yoursaas.com:443 -servername app.customer.com 2>/dev/null \
  | openssl x509 -noout -subject -issuer

# 4. Check for pending validations (any cert not yet active)
curl -s \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/custom_hostnames?ssl.status=pending_validation" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result | length'

# 5. Simulate tenant routing in Worker
npx wrangler tail saas-router --format=pretty
curl -H "Host: app.customer.com" https://yoursaas.com/health
```

## Related

- `cloudflare-pages-custom-domain-ssl.md` — simpler custom domain flow for Pages projects
- `workers-custom-domains.md` — Worker-level custom domains (not multi-tenant)
- `cloudflare-access-zero-trust-service-tokens.md` — protecting the origin behind the SaaS route
- `kv-eventually-consistent.md` — KV caching for hostname-to-tenant mapping
- `advanced-certificate-manager-total-tls.md` — certificate management alternatives

## Sources

- Cloudflare for SaaS overview: https://developers.cloudflare.com/cloudflare-for-platforms/cloudflare-for-saas/
- Custom Hostnames API: https://developers.cloudflare.com/cloudflare-for-platforms/cloudflare-for-saas/start/getting-started/
- SSL status fields: https://developers.cloudflare.com/cloudflare-for-platforms/cloudflare-for-saas/security/certificate-management/
- Wildcard custom hostnames: https://developers.cloudflare.com/cloudflare-for-platforms/cloudflare-for-saas/domain-support/wildcard-custom-hostnames/
- Terraform cloudflare_custom_hostname: https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/custom_hostname
