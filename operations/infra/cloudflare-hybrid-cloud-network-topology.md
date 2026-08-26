# Network Topology for Cloudflare + Hybrid Cloud

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

An organization runs stateful workloads (databases, ML inference, legacy
services) in AWS VPC or a private data center but wants to use Cloudflare
Workers at the edge for request handling, authentication, and fan-out.
Getting these two planes to communicate without exposing origin services to
the public internet requires deliberate network architecture, not an ad-hoc
tunnel bolted on later.

## Context

Cloudflare's edge network (2026) operates at 300+ Points of Presence worldwide.
Workers execute at the PoP closest to the user but must reach origin services
that live in regional cloud VPCs or on-premises racks. The connectivity options:

| Method | Latency | Auth | Bilateral | Use |
|--------|---------|------|-----------|-----|
| Public HTTPS to origin | Low | mTLS / JWT | No | Public origins |
| Cloudflare Tunnel (cloudflared) | Low | Zero Trust | Worker→origin only | Private services |
| Cloudflare Magic WAN | Very low | IPsec/GRE | Yes | SD-WAN / site mesh |
| Cloudflare Network Interconnect | Ultra-low | Physical/virtual | Yes | Enterprise data centers |
| Argo Smart Routing | Low | Standard | No | Latency optimization on public routes |

A typical mid-size SaaS topology uses Tunnel for outbound (Worker→origin) and
mTLS for inbound (origin→Worker API). Magic WAN or CNI is reserved for
dedicated data-center uplinks.

---

## Section 1: Cloudflare Tunnel for Private Origin Access

Tunnel lets Workers reach services that have no public IP by running a
lightweight `cloudflared` daemon in the origin network. The tunnel maintains
a persistent outbound connection to Cloudflare's edge; Workers connect through
the same path.

```bash
# Install cloudflared on the origin host
curl -L --output cloudflared.deb \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
dpkg -i cloudflared.deb

# Authenticate and create a named tunnel
cloudflared tunnel login
cloudflared tunnel create private-services

# Map hostnames to local services
cloudflared tunnel route dns private-services db.internal.company.com
cloudflared tunnel route dns private-services api.internal.company.com
```

Tunnel config at `/etc/cloudflared/config.yml`:

```yaml
tunnel: <TUNNEL_UUID>
credentials-file: /root/.cloudflared/<TUNNEL_UUID>.json

ingress:
  - hostname: db.internal.company.com
    service: tcp://127.0.0.1:5432
    originRequest:
      connectTimeout: 5s
      tcpKeepAlive: 30s

  - hostname: api.internal.company.com
    service: http://127.0.0.1:8080
    originRequest:
      http2Origin: true
      disableChunkedEncoding: false
      httpHostHeader: api.internal.company.com

  - service: http_status:404
```

From a Worker, reach private services using their Tunnel-bound hostnames:

```typescript
// Worker: proxy to private API via Tunnel
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const origin = new URL("https://api.internal.company.com");
    origin.pathname = url.pathname;
    origin.search = url.search;

    return fetch(origin.toString(), {
      method: req.method,
      headers: {
        ...Object.fromEntries(req.headers),
        "CF-Access-Client-Id": env.ACCESS_CLIENT_ID,
        "CF-Access-Client-Secret": env.ACCESS_CLIENT_SECRET,
      },
      body: req.method !== "GET" ? req.body : undefined,
    });
  },
};
```

The `CF-Access-Client-Id` / `CF-Access-Client-Secret` headers are Service
Tokens issued in Cloudflare Zero Trust and bound to an Access policy protecting
the Tunnel hostname.

---

## Section 2: mTLS for Origin-Initiated Requests

When the origin (AWS Lambda, EC2 service, or Kubernetes pod) needs to call a
Workers API, use mTLS to prove identity at the Cloudflare edge without routing
through a VPN.

```bash
# Generate a client certificate using Cloudflare's CA (mTLS API)
# 1. Create a mTLS CA (or import your own)
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/mtls_certificates" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "internal-services-ca",
    "ca": true,
    "certificates": "'"$(cat ca.pem)"'"
  }'

# 2. Create a mTLS rule on the zone to enforce client certs
curl -X POST "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/rulesets" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "mtls-internal",
    "kind": "zone",
    "phase": "http_request_firewall_custom",
    "rules": [{
      "action": "block",
      "expression": "(http.request.uri.path matches \"^/internal/\") and (not cf.tls_client_auth.cert_verified)",
      "description": "Require mTLS for internal API paths"
    }]
  }'
```

Golang origin service presenting a client certificate:

```go
// origin/client/mtls.go
package client

import (
    "crypto/tls"
    "crypto/x509"
    "net/http"
    "os"
)

func NewMTLSClient(certPath, keyPath string) (*http.Client, error) {
    cert, err := tls.LoadX509KeyPair(certPath, keyPath)
    if err != nil {
        return nil, err
    }

    rootCAs, _ := x509.SystemCertPool()
    transport := &http.Transport{
        TLSClientConfig: &tls.Config{
            Certificates: []tls.Certificate{cert},
            RootCAs:      rootCAs,
            MinVersion:   tls.VersionTLS13,
        },
    }

    return &http.Client{Transport: transport}, nil
}
```

On the Kubernetes side, mount the client certificate as a Secret and inject
it into pods via projected volumes:

```yaml
# k8s/origin-service/deployment.yaml
volumes:
  - name: mtls-cert
    secret:
      secretName: cloudflare-client-cert
      items:
        - key: tls.crt
          path: client.crt
        - key: tls.key
          path: client.key
containers:
  - name: origin-api
    volumeMounts:
      - name: mtls-cert
        mountPath: /etc/mtls
        readOnly: true
    env:
      - name: MTLS_CERT_PATH
        value: /etc/mtls/client.crt
      - name: MTLS_KEY_PATH
        value: /etc/mtls/client.key
```

---

## Section 3: Latency Budget and Routing Architecture

Map latency budgets before committing to a topology. A typical request
through Cloudflare + Tunnel:

```
User → CF PoP [0 ms]
  → Worker execution [1–5 ms CPU]
  → Tunnel handoff to cloudflared [1–3 ms, already-connected tunnel]
  → Origin service TCP [5–30 ms, depends on region proximity]
  → Response back through Tunnel [1–3 ms]
  → Response to user via CF PoP [0 ms]

Total origin leg: 7–40 ms added over a direct public HTTPS call
```

To minimize origin leg latency:

1. **Co-locate cloudflared in the same region as the Cloudflare PoP your zone uses**.
   Use `cloudflared tunnel info <UUID>` to see which Cloudflare data centers
   the tunnel connects to, and choose an AWS region geographically close.

2. **Run multiple cloudflared instances for HA**. Two daemons with the same
   `credentials-file` create two persistent connections; Cloudflare load-balances:

   ```bash
   # Both instances share credentials, run as separate systemd units
   systemctl enable --now cloudflared@primary
   systemctl enable --now cloudflared@secondary
   ```

3. **Use Smart Placement for Workers** to move Worker execution closer to the
   origin rather than the user when the CPU work is trivial but origin latency
   dominates:

   ```toml
   # wrangler.toml
   [placement]
   mode = "smart"
   ```

4. **Cache aggressively at the edge** using the Cache API to avoid round-trips
   to origin for deterministic responses:

   ```typescript
   const cacheKey = new Request(req.url, req);
   const cached = await caches.default.match(cacheKey);
   if (cached) return cached;

   const response = await fetchFromOrigin(req, env);
   const toCache = new Response(response.body, response);
   toCache.headers.set("Cache-Control", "s-maxage=60");
   ctx.waitUntil(caches.default.put(cacheKey, toCache));
   return response;
   ```

Network topology diagram (conceptual):

```
         ┌──────────────────────────────────────────┐
         │         Cloudflare Global Network         │
         │                                           │
User ───►│  PoP (Frankfurt) ──► Worker Execution    │
         │         │                                 │
         │         │ Tunnel (persistent outbound)    │
         └─────────┼───────────────────────────────-─┘
                   │
                   ▼
         ┌─────────────────────────────┐
         │    AWS eu-central-1 VPC     │
         │                             │
         │  cloudflared ──► Origin API │
         │                  │          │
         │                  ▼          │
         │             RDS PostgreSQL  │
         └─────────────────────────────┘
```

---

## Anti-patterns

- **Disabling Cloudflare's proxy (grey-cloud DNS)** to let Workers reach origin
  directly: this exposes the origin IP, defeating the security benefit of routing
  through Cloudflare. Keep all origins behind orange-cloud (proxied) DNS.
- **Using Tunnel for high-bandwidth bulk transfers**: Tunnel is optimized for
  request-response patterns. Streaming large files or database dumps through Tunnel
  creates backpressure on the daemon. Use a pre-signed R2 URL or direct VPC link
  for bulk data.
- **Single cloudflared instance**: one daemon is a single point of failure. Always
  run at least two in separate availability zones.
- **Hardcoding Cloudflare data-center addresses**: Cloudflare's PoP IPs are dynamic.
  Filter inbound traffic by Cloudflare's published IP ranges (available via API),
  not hardcoded CIDRs.
- **Using Magic WAN before proving Tunnel is insufficient**: Magic WAN has setup
  complexity and cost. Start with Tunnel; upgrade only when latency or bandwidth
  measurements justify it.

---

## Gotchas

- Cloudflare Tunnel routes DNS to `<tunnel-id>.cfargotunnel.com` behind the scenes.
  If you delete and recreate a tunnel with the same name, DNS CNAME records must
  be updated to the new tunnel ID.
- TCP services exposed via Tunnel (like PostgreSQL) require `cloudflared access tcp`
  on the client side to proxy the connection; Workers cannot natively speak TCP
  to Tunnel—only HTTP/WebSocket ingress is supported from Workers to Tunnel.
- Smart Placement moves the Worker's compute but not the `request.cf.colo`
  header value. Do not use that header to infer where your code is running when
  Smart Placement is active.
- mTLS certificate validation at the Cloudflare edge does not forward the verified
  certificate's CN or SAN to the Worker by default. Use `cf.tls_client_auth`
  fields in Ruleset Engine expressions or read headers in the Worker to extract
  identity claims.
- Magic WAN and Cloudflare Tunnel are mutually exclusive per-route; you cannot
  have the same private IP range reachable via both simultaneously.

---

## Verification

```bash
# Verify tunnel is active and connected to multiple Cloudflare data centers
cloudflared tunnel info <TUNNEL_UUID>

# Test private hostname resolution from inside the VPC
dig api.internal.company.com  # should resolve to 100.96.0.0/12 (Cloudflare Tunnel range)

# Test mTLS enforcement: request without cert should be blocked
curl -v https://api.company.com/internal/health  # expect 403

# Test with client cert
curl -v --cert client.crt --key client.key https://api.company.com/internal/health  # expect 200

# Measure Worker-to-origin latency via tail logs
wrangler tail my-worker --format json | jq '.logs[] | select(.message | contains("origin_ms"))'

# Cloudflare IP ranges (for origin firewall rules)
curl -s https://api.cloudflare.com/client/v4/ips | jq '.result.ipv4_cidrs[]'
```

---

## Related

- `/documentation/categories/infra/cloudflare-tunnel-private-services.md`
- `/documentation/categories/infra/zero-trust-network-access.md`
- `/documentation/categories/infra/tls-termination-architecture.md`
- `/documentation/categories/infra/ssl-tls-certificate-management.md`
- `/documentation/categories/infra/multi-cloud-strategy.md`

---

## Sources

- Cloudflare Tunnel architecture: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
- Cloudflare mTLS: https://developers.cloudflare.com/ssl/client-certificates/
- Workers Smart Placement: https://developers.cloudflare.com/workers/configuration/smart-placement/
- Magic WAN overview: https://developers.cloudflare.com/magic-wan/
- Cloudflare IP ranges API: https://api.cloudflare.com/#cloudflare-ips-properties
