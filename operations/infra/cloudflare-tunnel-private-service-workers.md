# Cloudflare Tunnel for Private Service Access from Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You have a private internal service (e.g., a database REST API, an internal gRPC gateway, a legacy monolith) that must not be exposed to the public internet, yet a Cloudflare Worker needs to call it. Standard `fetch()` from a Worker only reaches public endpoints, so you need a secure tunnel that bridges the gap without poking holes in your firewall or assigning public IPs.

---

## Context
Cloudflare Tunnel (`cloudflared`) establishes an outbound-only encrypted connection from your private network to Cloudflare's edge. The tunnel exposes the internal service under a Cloudflare-managed hostname, optionally protected by Cloudflare Access (Zero Trust). A Worker can then call that hostname via a service binding or a plain `fetch()`, with mTLS certificates ensuring mutual authentication between the Worker and the tunnel. Local development is supported by running `cloudflared` locally and pointing `wrangler dev --service` at the tunnel URL. This pattern eliminates public IPs, VPNs, and firewall rules for service-to-service calls.

---

## Section 1 — Tunnel and Access Config

```yaml
# ~/.cloudflared/config.yml  (runs on the host inside your private network)
tunnel: <your-tunnel-uuid>
credentials-file: /etc/cloudflared/<your-tunnel-uuid>.json

ingress:
  - hostname: internal-api.example.com
    service: http://localhost:8080
    originRequest:
      # Enforce mTLS — Workers present a client cert issued by your CA
      tlsTimeout: 10s
      connectTimeout: 10s
  - service: http_status:404
```

```bash
# Create the tunnel (run once)
cloudflared tunnel create internal-api

# Route DNS — creates a CNAME in your Cloudflare zone
cloudflared tunnel route dns internal-api internal-api.example.com

# Create a Cloudflare Access application protecting the tunnel hostname
# (done via Terraform — see Section 2)

# Run the tunnel daemon
cloudflared tunnel run internal-api
```

## Section 2 — Terraform: Access Policy + Worker Service Binding

```hcl
# terraform/tunnel.tf
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
}

variable "cloudflare_account_id" {}
variable "cloudflare_zone_id" {}
variable "tunnel_secret" { sensitive = true }

resource "cloudflare_zero_trust_tunnel_cloudflared" "internal_api" {
  account_id = var.cloudflare_account_id
  name       = "internal-api"
  secret     = <redacted-secret>
}

resource "cloudflare_zero_trust_access_application" "internal_api" {
  account_id       = var.cloudflare_account_id
  name             = "Internal API Tunnel"
  domain           = "internal-api.example.com"
  session_duration = "24h"
  type             = "self_hosted"
}

resource "cloudflare_zero_trust_access_policy" "workers_service_token" {
  account_id     = var.cloudflare_account_id
  application_id = cloudflare_zero_trust_access_application.internal_api.id
  name           = "Workers Service Token"
  precedence     = 1
  decision       = "non_identity"

  include {
    service_token = [cloudflare_zero_trust_access_service_token.worker.id]
  }
}

resource "cloudflare_zero_trust_access_service_token" "worker" {
  account_id = var.cloudflare_account_id
  name       = "internal-api-worker-token"
  min_days_for_renewal = 30
}

resource "cloudflare_mtls_certificate" "worker_client" {
  account_id   = var.cloudflare_account_id
  name         = "worker-mtls-client"
  certificates = file("certs/worker-client.pem")
  ca           = true
}
```

## Section 3 — Worker Implementation and Local Dev

```typescript
// src/index.ts
export interface Env {
  // Service binding to the tunneled hostname (configured in wrangler.toml)
  INTERNAL_API: Fetcher;
  CF_ACCESS_CLIENT_ID: string;
  CF_ACCESS_CLIENT_SECRET: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Forward the original path to the internal service
    const url = new URL(request.url);
    const internalPath = url.pathname + url.search;

    // When using a service binding, the hostname is resolved by Cloudflare;
    // Access service token headers are injected automatically if configured.
    // For plain fetch() fallback (e.g., during local dev without binding):
    const targetUrl = `https://internal-api.example.com${internalPath}`;

    let response: Response;
    if (env.INTERNAL_API) {
      // Service binding path — fastest, no egress charges
      response = await env.INTERNAL_API.fetch(
        new Request(targetUrl, {
          method: request.method,
          headers: request.headers,
          body: request.body,
        })
      );
    } else {
      // Fallback: direct fetch with Access service token
      const headers = new Headers(request.headers);
      headers.set("CF-Access-Client-Id", env.CF_ACCESS_CLIENT_ID);
      headers.set("CF-Access-Client-Secret", env.CF_ACCESS_CLIENT_SECRET);
      response = await fetch(targetUrl, {
        method: request.method,
        headers,
        body: request.body,
      });
    }

    // Strip internal headers before returning to client
    const cleaned = new Response(response.body, response);
    cleaned.headers.delete("CF-Ray");
    cleaned.headers.delete("CF-Cache-Status");
    return cleaned;
  },
};
```

```toml
# wrangler.toml
name = "tunnel-proxy-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[services]]
binding = "INTERNAL_API"
service = "internal-api-worker"
environment = "production"

[vars]
CF_ACCESS_CLIENT_ID = "<your-service-token-client-id>.access"

[secrets]
# Set via: wrangler secret put CF_ACCESS_CLIENT_SECRET
CF_ACCESS_CLIENT_SECRET = ""
```

```bash
# Local dev: run cloudflared in a separate terminal
cloudflared tunnel --url http://localhost:8080 --name dev-tunnel

# Then start the worker pointing at the local tunnel URL
wrangler dev --local

# To test the service binding locally, run both workers:
wrangler dev --service internal-api-worker=http://localhost:8080
```

---

## Anti-patterns
- **Exposing the tunnel hostname publicly without Access** — anyone can call your internal service; always attach an Access application.
- **Hardcoding service token secrets in wrangler.toml** — use `wrangler secret put` so secrets are stored encrypted in Cloudflare, not in version control.
- **Using a single tunnel for multiple unrelated services** — separate tunnels per service boundary makes revocation and debugging much cleaner.
- **Skipping mTLS** — service token headers can be spoofed at the network level; mTLS provides cryptographic mutual authentication.

---

## Gotchas
- `cloudflared` must be version ≥ 2024.x to support `--service` flag in local dev; check with `cloudflared version`.
- Service bindings are only supported for Workers on the same Cloudflare account.
- The Access service token has an expiry (`min_days_for_renewal`); set up a Terraform workflow or cron to rotate before expiry.
- `request.body` is a `ReadableStream` and can only be consumed once; clone the request if you need to read the body and also forward it.

---

## Verification

```bash
# Confirm tunnel is active
cloudflared tunnel info internal-api

# Test Access policy (should get 403 without service token)
curl -i https://internal-api.example.com/health

# Test with service token headers
curl -i \
  -H "CF-Access-Client-Id: ${CLIENT_ID}" \
  -H "CF-Access-Client-Secret: ${CLIENT_SECRET}" \
  https://internal-api.example.com/health

# Verify Worker can reach the tunnel
curl -i https://tunnel-proxy-worker.<subdomain>.workers.dev/health

# Check tunnel metrics in Cloudflare dashboard
# Zero Trust → Access → Tunnels → internal-api → Metrics
```

---

## Related
- `workers-load-balancer-health-check-kv.md`
- `terraform-cloudflare-workers-kv-r2.md`

---

## Sources
- Cloudflare Tunnel documentation — https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
- Cloudflare Access Service Tokens — https://developers.cloudflare.com/cloudflare-one/identity/service-tokens/
- Workers Service Bindings — https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
