# Cloudflare Zero Trust WARP-to-WARP Private Networking

- Date: 2026-08-22
- Author: example.com
- Status: production

## Problem: Giving Workers and remote devices access to private services without a VPN gateway

Traditional VPNs require a central gateway that becomes a bottleneck and single point of failure.
Cloudflare WARP-to-WARP tunnels private traffic directly through Cloudflare's network: enrolled
devices and Cloudflare Workers (via service tokens) reach internal services by IP or private
hostname without any open inbound port on the service host.

The key problem is coordinating three things: split tunnels that define which CIDR ranges route
through Cloudflare, device posture policies that gate access per-application, and private DNS
resolution so that `internal.corp` resolves correctly without leaking to public DNS. Getting any
one of these wrong produces silent routing failures that are hard to diagnose.

This article covers the full configuration: WARP client split tunnel setup, device posture
enforcement, private DNS, and how a Workers service consumes a private HTTP endpoint using a
Cloudflare service token and Access mutual TLS.

## Context

- Cloudflare Zero Trust plan (Teams or Enterprise for posture checks)
- WARP client 2024.x on macOS/Windows/Linux
- Private network CIDR: `10.20.0.0/16`, private DNS zone: `internal.corp`
- Cloudflare Tunnel (`cloudflared`) running on the private network host
- Workers consuming private service via Access service token

## Split Tunnel Configuration

Split tunnels tell the WARP client which traffic to route through Cloudflare versus the local
network stack. Use "Exclude" mode (default) and add your private CIDR to the Include list, or
switch the device profile to "Include Only" mode for tighter control.

Configure via Zero Trust dashboard → Settings → WARP Client → Device profiles → Split Tunnels:

```
Mode: Include Only
Include routes:
  10.20.0.0/16      # private services
  100.64.0.0/10     # Cloudflare internal IP range (required for WARP-to-WARP)

Private DNS suffix: internal.corp → resolver: 10.20.0.2 (your internal DNS)
```

Or via the Cloudflare API:

```bash
# List device profiles
curl "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/devices/policy" \
  -H "Authorization: Bearer ${CF_API_TOKEN}"

# Update split tunnel for a profile
curl -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/devices/policy/${POLICY_ID}/tunnel_split_dns" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"entries":[{"address":"internal.corp","description":"Internal DNS"}]}'
```

## Device Posture Checks

Gate access to sensitive private applications behind posture rules. Zero Trust evaluates posture
at connection time; failing devices are denied at the Access policy level.

```jsonc
// Zero Trust → Access → Applications → internal-api.internal.corp
// Policy:
{
  "name": "Employees with healthy device",
  "decision": "allow",
  "include": [
    { "email_domain": { "domain": "corp.example.com" } }
  ],
  "require": [
    { "device_posture": { "integration_uid": "DISK_ENCRYPTION_CHECK_UID" } },
    { "device_posture": { "integration_uid": "OS_VERSION_CHECK_UID" } }
  ]
}
```

Supported posture providers: Intune, Jamf, CrowdStrike, SentinelOne, and Cloudflare's built-in
checks (disk encryption, OS version, firewall, serial number allow-list).

## Private DNS Resolution

`cloudflared` on the private network registers a DNS-over-HTTPS (DoH) resolver for your private
zone. Zero Trust Local Domain Fallback routes queries matching `*.internal.corp` to this resolver
instead of public DNS.

```yaml
# cloudflared tunnel config (on private network host)
tunnel: YOUR_TUNNEL_ID
credentials-file: /etc/cloudflared/credentials.json

ingress:
  - hostname: internal-api.internal.corp
    service: http://localhost:8080
  - hostname: dns.internal.corp
    service: https://10.20.0.2:853   # internal DoH resolver
  - service: http_status:404
```

```bash
# Install and run
cloudflared service install
cloudflared tunnel run YOUR_TUNNEL_NAME
```

## Workers Accessing Private Services via Service Token

Workers run outside of enrolled devices; they authenticate to Access-protected private endpoints
using a Cloudflare Access service token (client ID + secret).

```ts
// src/private-service-client.ts
interface Env {
  ACCESS_CLIENT_ID: string;      // wrangler secret put ACCESS_CLIENT_ID
  ACCESS_CLIENT_SECRET: string;  // wrangler secret put ACCESS_CLIENT_SECRET
}

const PRIVATE_API_BASE = 'https://internal-api.internal.corp';

export async function callPrivateService(
  path: string,
  env: Env,
  init?: RequestInit
): Promise<Response> {
  const url = `${PRIVATE_API_BASE}${path}`;

  const response = await fetch(url, {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
      'CF-Access-Client-Id': env.ACCESS_CLIENT_ID,
      'CF-Access-Client-Secret': env.ACCESS_CLIENT_SECRET,
      'Content-Type': 'application/json',
    },
  });

  if (response.status === 403) {
    throw new Error(`Access denied to private service: ${url}. Check service token policy.`);
  }

  return response;
}

// Usage in a Worker fetch handler
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const data = await callPrivateService('/api/v1/internal-data', env);
    return new Response(data.body, {
      status: data.status,
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

The service token must be added to the Access application policy with decision `service_auth`:

```jsonc
{
  "name": "Workers service account",
  "decision": "service_auth",
  "include": [
    { "service_token": { "token_uuid": "YOUR_SERVICE_TOKEN_UUID" } }
  ]
}
```

## Anti-patterns

- Do not use "Exclude" split tunnel mode and rely on adding every private CIDR manually — switch to "Include Only" for private-network-only WARP profiles
- Do not expose the cloudflared tunnel's management port (port 8080) to the public internet
- Do not store Access service token secrets in `wrangler.toml` — always use `wrangler secret put`
- Do not skip device posture on applications accessible from WARP — any enrolled device gains access without posture gates

## Gotchas

- WARP-to-WARP requires both devices/services to be enrolled in the **same Zero Trust organization**; cross-org is not supported
- Private DNS Local Domain Fallback does not apply when the device is on "Direct" mode (WARP disabled); ensure fallback behavior is documented for users
- Cloudflare Tunnel hostname must exactly match the Access application hostname including subdomain
- Service tokens expire; set a rotation reminder and update the Worker secret before expiry to avoid 403s

## Verification

```ts
// From a WARP-enrolled device, confirm private DNS resolves
// $ nslookup internal-api.internal.corp
// Should return: 100.96.x.x (WARP virtual IP)

// From a Worker, health-check the private endpoint
export default {
  async fetch(_request: Request, env: Env): Promise<Response> {
    const start = Date.now();
    const res = await callPrivateService('/health', env);
    const latency = Date.now() - start;
    const body = await res.text();
    return Response.json({ status: res.status, latency_ms: latency, body });
  },
};
```

## Related

- documentation/docs/policies/cloudflare/zero-trust-access-policies.md
- documentation/docs/policies/cloudflare/cloudflare-tunnel-best-practices.md
- documentation/docs/policies/cloudflare/warp-connector.md
- documentation/docs/policies/cloudflare/workers-secrets-best-practices.md

## Sources

- https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/private-net/warp-to-warp/
- https://developers.cloudflare.com/cloudflare-one/identity/devices/
- https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/private-net/cloudflared/
- https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/self-hosted-apps/
- https://developers.cloudflare.com/cloudflare-one/identity/service-tokens/
