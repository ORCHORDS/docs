# Cloudflare Workers Outbound IP Allowlisting Strategies

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

An upstream third-party API, internal firewall, or database allowlist requires you to
restrict inbound traffic to known source IPs. Your Cloudflare Workers make outbound
`fetch()` calls to those services and the upstream rejects requests because Workers
do not originate from a static set of IPs — they egress from Cloudflare's global
anycast network, which publishes hundreds of prefixes and rotates over time.

## Context

Cloudflare publishes its IP ranges at `https://api.cloudflare.com/client/v4/ips` (JSON)
and `https://www.cloudflare.com/ips-v4` / `ips-v6` (plain text). Workers egress through
the same ranges used for proxied HTTP traffic; there is no separate "Workers egress" CIDR
list. The full list is large (~30 IPv4 CIDRs, ~6 IPv6 CIDRs as of mid-2026) and changes
without advance notice — pinning individual addresses is not supported. Three practical
strategies exist: proxy egress through a known fixed IP, push auth into the request layer,
or use Cloudflare's own network controls to constrain the upstream.

---

## Strategy 1 — Tunnel + Private Network Egress (Recommended)

Route Worker subrequests through a `cloudflared` connector that terminates inside your
network. The upstream firewall sees the connector host IP, not a Cloudflare anycast address.

```typescript
// worker/src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Internal hostname resolves via Zero Trust private network DNS
    const upstream = new URL("https://internal-api.corp.example.com/data");
    upstream.searchParams.set("q", new URL(request.url).searchParams.get("q") ?? "");

    const resp = await fetch(upstream.toString(), {
      headers: {
        // Service token injected as a secret
        "CF-Access-Client-Id": env.ACCESS_CLIENT_ID,
        "CF-Access-Client-Secret": env.ACCESS_CLIENT_SECRET,
      },
      // Workers do not support keepalive; timeout via AbortSignal
      signal: AbortSignal.timeout(5_000),
    });

    if (!resp.ok) {
      return new Response(`upstream error ${resp.status}`, { status: 502 });
    }

    return new Response(resp.body, {
      status: resp.status,
      headers: { "Content-Type": resp.headers.get("Content-Type") ?? "application/json" },
    });
  },
};
```

The `cloudflared` tunnel connector runs on a host whose IP you allowlist in the upstream
firewall. Zero Trust Access validates the service token before traffic reaches the internal
host — no public internet exposure required.

---

## Strategy 2 — Smart Placement + Dedicated Egress Add-on

Cloudflare's **Dedicated Egress IPs** add-on (enterprise) assigns static IPv4 addresses to
a subset of PoPs. Smart Placement pins the Worker to those PoPs when latency allows.

```typescript
// wrangler.toml excerpt
// [placement]
// mode = "smart"   # Worker co-locates near the upstream, which must be one of the
//                  # PoPs covered by your Dedicated Egress IP subscription.
```

Dedicated Egress IPs are provisioned per account and per location; contact your CSM to
obtain the addresses, then allowlist them at the upstream.

```typescript
// worker/src/index.ts
export default {
  async fetch(_request: Request, env: Env): Promise<Response> {
    // With Dedicated Egress, this request will exit from the assigned static IP
    // when Smart Placement selects an eligible colo.
    const resp = await fetch("https://partner-api.example.com/v1/orders", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.PARTNER_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ source: "workers" }),
    });
    return resp;
  },
};
```

---

## Strategy 3 — mTLS Client Certificate (Identity, Not IP)

Replace IP-based allowlisting with certificate-based identity. The upstream validates the
client cert instead of the source address — far more robust and zero maintenance on IP changes.

```typescript
// worker/src/index.ts
// Requires: "mtls_certificates" binding in wrangler.toml
//   [[mtls_certificates]]
//   binding = "CLIENT_CERT"
//   certificate_id = "<cert-uuid-from-dashboard>"

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const resp = await fetch("https://secure-upstream.example.com/api", {
      // @ts-expect-error: Workers-specific fetch option
      cf: { mtlsClientCert: env.CLIENT_CERT },
      headers: { "Content-Type": "application/json" },
      body: request.body,
      method: "POST",
    });
    return resp;
  },
};
```

Upload the client certificate via the dashboard (SSL/TLS → Client Certificates → mTLS) or
Terraform, then configure the upstream to require and validate the CA chain.

---

## Strategy 4 — Egress Proxy Worker (IP Normalization)

Deploy a proxy Worker on a zone whose IPs are already allowlisted, or route through an
intermediate VPS with a fixed IP using a persistent outbound connection via Cloudflare
Hyperdrive or a plain TCP socket (not available in Workers today) — use a lightweight
Node.js/Bun proxy on a fixed VPS instead.

```typescript
// proxy/server.ts (runs on a VPS with allowlisted IP, e.g. 203.0.113.42)
import { createServer } from "node:http";

const UPSTREAM = "https://restricted-api.example.com";

createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", UPSTREAM);
  const upstream = await fetch(url.toString(), {
    method: req.method,
    headers: Object.fromEntries(
      Object.entries(req.headers).filter(([k]) => k !== "host")
    ) as Record<string, string>,
    body: req.method !== "GET" ? req : undefined,
    // @ts-expect-error: Node fetch duplex
    duplex: "half",
  });
  res.writeHead(upstream.status, Object.fromEntries(upstream.headers));
  upstream.body?.pipeTo(new WritableStream({
    write(chunk) { res.write(chunk); },
    close() { res.end(); },
  }));
}).listen(8080);
```

Your Worker then fetches `https://proxy.internal.example.com/…` which is routed via
a Cloudflare Tunnel back to the VPS — the upstream sees the VPS IP.

---

## Strategy 5 — Dynamic Cloudflare IP Fetch + Upstream Automation

If you control the upstream firewall (e.g., AWS Security Group, GCP VPC firewall), automate
allowlist updates using the Cloudflare IP API rather than maintaining a static list.

```typescript
// scripts/sync-cf-ips.ts  (runs in a Worker cron or a GitHub Actions job)
interface CloudflareIPResponse {
  result: { ipv4_cidrs: string[]; ipv6_cidrs: string[]; etag: string };
  success: boolean;
}

async function fetchCloudflareIPs(): Promise<{ v4: string[]; v6: string[] }> {
  const resp = await fetch("https://api.cloudflare.com/client/v4/ips", {
    headers: { Accept: "application/json" },
  });
  if (!resp.ok) throw new Error(`CF IPs fetch failed: ${resp.status}`);
  const data = (await resp.json()) as CloudflareIPResponse;
  return {
    v4: data.result.ipv4_cidrs,
    v6: data.result.ipv6_cidrs,
  };
}

// Use AWS SDK / GCP client to sync into your Security Group / VPC Firewall here.
export { fetchCloudflareIPs };
```

Store the `etag` in KV; only call the firewall API when the etag changes to avoid
rate-limit churn.

---

## Anti-patterns

- **Allowlisting individual Cloudflare IPs** — IPs rotate without notice. Never pin
  individual addresses; always use the full published CIDR list or prefer mTLS.
- **Disabling firewall rules "temporarily"** — teams that disable upstream allowlists
  while debugging rarely re-enable them. Use time-boxed Security Group rules instead.
- **Storing upstream credentials only in wrangler.toml** — secrets must be in Workers
  Secrets (via `wrangler secret put`), not in plaintext config committed to the repo.
- **Ignoring IPv6** — Cloudflare publishes IPv6 CIDRs. Upstreams that filter only IPv4
  may accept Workers requests over IPv6 unintentionally.

---

## Gotchas

- Dedicated Egress IPs are bound to specific PoPs; if Smart Placement routes to a
  non-covered PoP the egress IP reverts to anycast. Validate with a `cf-ray` header
  check against covered colo codes.
- `AbortSignal.timeout()` in Workers is the correct pattern for subrequest timeouts;
  `setTimeout` is not available in the Workers runtime.
- mTLS bindings require the certificate to be uploaded to the account that owns the
  Worker; certificates in other accounts are not accessible even in multi-account setups.
- Cloudflare Tunnel connectors must have WARP routing or private DNS configured before
  Worker subrequests can resolve internal hostnames via Zero Trust.

---

## Verification

```bash
# 1. Confirm Cloudflare published IP ranges
curl -s https://api.cloudflare.com/client/v4/ips | jq '.result | {v4: .ipv4_cidrs | length, v6: .ipv6_cidrs | length}'

# 2. Test mTLS from a Worker (check upstream access logs for cert CN)
wrangler dev --local false
curl "https://<worker-subdomain>.workers.dev/test-mtls"

# 3. Verify egress IP when using Dedicated Egress (enterprise)
curl -s https://ifconfig.me   # called from inside the Worker via a test endpoint
# Should return one of the dedicated IPs, not a dynamic anycast address.

# 4. Validate tunnel reachability
wrangler tunnel run <tunnel-name> --loglevel debug
```

---

## Related

- `cloudflare-tunnel-private-services.md`
- `cloudflare-mtls-client-certificates-terraform.md`
- `cloudflare-access-jwt-workers-validation.md`
- `cloudflare-workers-api-token-scoping.md`
- `hyperdrive-postgresql-pulumi-iac.md`

---

## Sources

- Cloudflare Docs — Dedicated Egress IPs: https://developers.cloudflare.com/cloudflare-one/policies/gateway/egress-policies/dedicated-egress-ips/
- Cloudflare IP Ranges API: https://api.cloudflare.com/client/v4/ips
- Cloudflare Docs — mTLS in Workers: https://developers.cloudflare.com/workers/runtime-apis/bindings/mtls/
- Cloudflare Docs — Cloudflare Tunnel: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
- Cloudflare Docs — Smart Placement: https://developers.cloudflare.com/workers/configuration/smart-placement/
