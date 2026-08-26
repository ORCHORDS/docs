# Cloudflare Tunnel for Self-Hosted Runners and Private Services

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

Self-hosted CI runners and internal services — staging APIs, admin dashboards, internal Next.js preview servers — need to be reachable by Cloudflare's network or by teammates without opening inbound ports on the host firewall or VPC security group. NAT, dynamic IPs, and strict egress-only policies block traditional port-forwarding approaches and expose machines to internet-wide scanning when inbound ports are opened.

## Context

example project runs its Next.js web app and React Native CI builds on a mix of cloud VMs and bare-metal runners. Cloudflare Tunnel (`cloudflared`) creates persistent, outbound-only connections from any host to Cloudflare's edge PoPs, letting Workers, Pages Functions, and the Zero Trust gateway route traffic back through the tunnel with no inbound firewall rules required. This is the canonical pattern for accessing private staging databases, internal admin APIs, and ephemeral preview environments from Cloudflare Workers via fetch or through the Zero Trust WARP client on mobile devices. Tunnel connections terminate at two or more Cloudflare PoPs simultaneously for redundancy.

## Installing and Authenticating cloudflared

```bash
# Debian/Ubuntu (apt repository method)
curl -L https://pkg.cloudflare.com/cloudflare-main.gpg | \
  sudo gpg --dearmor -o /usr/share/keyrings/cloudflare-main.gpg

echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] \
  https://pkg.cloudflare.com/cloudflared jammy main' | \
  sudo tee /etc/apt/sources.list.d/cloudflared.list

sudo apt update && sudo apt install cloudflared

# Verify install
cloudflared --version

# Authenticate — opens browser to choose Cloudflare zone
cloudflared tunnel login
# Writes cert: ~/.cloudflared/cert.pem
```

For headless servers and CI environments authenticate with an API token instead of interactive login:

```bash
# Generate a Cloudflare API token with:
#   Zone > DNS > Edit
#   Account > Cloudflare Tunnel > Edit
export CLOUDFLARE_API_TOKEN="<token>"
export CLOUDFLARE_ACCOUNT_ID="<account-id>"

# Create tunnel non-interactively (uses env vars)
cloudflared tunnel create example project-staging
# Writes credentials JSON: ~/.cloudflared/<UUID>.json
```

## Creating and Configuring a Named Tunnel

```bash
# Create once per environment; reuse across restarts
cloudflared tunnel create example project-runners-prod
# Output: Tunnel ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890

# List all tunnels in the account
cloudflared tunnel list

# Delete a stale tunnel (must have no active connections)
cloudflared tunnel delete <tunnel-id> --force
```

Tunnel configuration file at `/etc/cloudflared/config.yml`:

```yaml
tunnel: a1b2c3d4-e5f6-7890-abcd-ef1234567890
credentials-file: /etc/cloudflared/a1b2c3d4-e5f6-7890-abcd-ef1234567890.json

# Metrics endpoint for Prometheus scraping
metrics: 0.0.0.0:2000

ingress:
  # Internal Next.js preview server
  - hostname: preview.internal.example project.example.com
    service: http://localhost:3000
    originRequest:
      connectTimeout: 10s
      noTLSVerify: false
      keepAliveConnections: 10
      keepAliveTimeout: 90s

  # Internal REST API gateway
  - hostname: api-internal.example project.example.com
    service: http://localhost:8080
    originRequest:
      httpHostHeader: api-internal.example project.example.com
      disableChunkedEncoding: false

  # TCP passthrough for PostgreSQL (private network mode)
  - hostname: db-private.example project.example.com
    service: tcp://localhost:5432

  # Catch-all rule — required at the end; returns 404
  - service: http_status:404
```

## DNS Routing Through Cloudflare

Create CNAME records that point to the tunnel's anycast hostname:

```bash
# Create DNS CNAME for each ingress hostname
cloudflared tunnel route dns example project-runners-prod preview.internal.example project.example.com
cloudflared tunnel route dns example project-runners-prod api-internal.example project.example.com

# For private network access (Zero Trust WARP clients and Workers)
# Route a private CIDR through the tunnel
cloudflared tunnel route ip add 10.0.0.0/8 a1b2c3d4-e5f6-7890-abcd-ef1234567890

# Verify the CNAME was created (proxied/orange-cloud)
cloudflare-cli dns list --zone example.com | grep CNAME
# preview.internal  CNAME  a1b2c3d4...cfargotunnel.com  proxied
```

## Running as a systemd Service

```bash
# Install the system service (copies config, creates unit file)
sudo cloudflared --config /etc/cloudflared/config.yml service install

sudo systemctl enable cloudflared
sudo systemctl start cloudflared
sudo systemctl status cloudflared

# Follow logs
sudo journalctl -u cloudflared -f --output cat
```

For hosts running multiple isolated runner tunnels, use a parameterized unit:

```ini
# /etc/systemd/system/cloudflared-runner@.service
[Unit]
Description=Cloudflare Tunnel — runner instance %i
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=notify
ExecStart=/usr/bin/cloudflared tunnel \
    --config /etc/cloudflared/runner-%i.yml run
Restart=on-failure
RestartSec=5s
TimeoutStartSec=0
KillMode=process
User=cloudflared
Group=cloudflared

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start two runner tunnel instances
sudo systemctl enable cloudflared-runner@node-1 cloudflared-runner@node-2
sudo systemctl start  cloudflared-runner@node-1 cloudflared-runner@node-2
```

## Cloudflare Workers Integration via Private Network

Workers can reach tunnel-exposed services when the private network CIDR is routed through the tunnel in the same Cloudflare account. No service binding is needed — plain `fetch` to a private IP resolves through the tunnel:

```typescript
// src/index.ts — Worker fetching an internal service via tunnel private network
export interface Env {
  INTERNAL_TOKEN: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Reaches the host at 10.0.1.50:8080 via the cloudflared private network route
    const upstream = await fetch('http://10.0.1.50:8080/api/status', {
      headers: {
        'X-Internal-Token': env.INTERNAL_TOKEN,
        'X-Request-ID': crypto.randomUUID(),
      },
      signal: AbortSignal.timeout(5000),
    });

    if (!upstream.ok) {
      return new Response('upstream error', { status: 502 });
    }

    const body = await upstream.json();
    return Response.json(body);
  },
} satisfies ExportedHandler<Env>;
```

Workers access to private networks must be enabled at the account level — contact Cloudflare support or enable through Zero Trust > Settings > Network > Proxy.

## GitHub Actions Self-Hosted Runner Tunnel Workflow

Self-hosted runners communicate outbound to GitHub (no tunnel required for that). Use the tunnel to expose services the runner starts during a job (preview deployments, integration test servers):

```yaml
# .github/workflows/preview.yml
jobs:
  preview:
    runs-on: [self-hosted, bare-metal, linux]
    steps:
      - uses: actions/checkout@v4

      - name: Start preview server
        run: |
          pnpm build && pnpm start &
          # Wait for server to be ready
          timeout 30 bash -c 'until curl -sf http://localhost:3000; do sleep 1; done'

      - name: Start ephemeral tunnel for QA
        run: |
          cloudflared tunnel --url http://localhost:3000 \
            --name example project-pr-${{ github.event.pull_request.number }} \
            --no-autoupdate &
          echo "TUNNEL_PID=$!" >> $GITHUB_ENV

      - name: Run Playwright tests against tunnel URL
        run: |
          TUNNEL_URL=$(cloudflared tunnel info \
            example project-pr-${{ github.event.pull_request.number }} \
            --output json | jq -r '.url')
          PLAYWRIGHT_BASE_URL="$TUNNEL_URL" pnpm test:e2e

      - name: Tear down tunnel
        if: always()
        run: kill $TUNNEL_PID || true
```

## Zero Trust Access Policy for Tunnel Services

Protect internal tunnel-exposed applications with Cloudflare Access so only authenticated teammates can reach them:

```hcl
# terraform/modules/tunnel-access/main.tf
resource "cloudflare_access_application" "preview" {
  zone_id          = var.zone_id
  name             = "example project Preview Servers"
  domain           = "preview.internal.example project.example.com"
  type             = "self_hosted"
  session_duration = "24h"
  logo_url         = "https://example.com/logo.png"
}

resource "cloudflare_access_policy" "engineering" {
  application_id = cloudflare_access_application.preview.id
  zone_id        = var.zone_id
  name           = "Engineering Team"
  precedence     = 1
  decision       = "allow"

  include {
    email_domain = ["example.com"]
  }

  require {
    device_posture = ["device-compliant-check-id"]
  }
}
```

## Mobile vs Desktop Considerations

example project serves both a React Native mobile app and a Next.js web app. Tunnel access patterns differ per platform:

- **Mobile (React Native QA)**: Install Cloudflare WARP on the test device. The WARP client routes traffic through the Zero Trust private network, reaching tunnel-exposed staging APIs at 10.x addresses without VPN config. No browser flow required.
- **Desktop (browser-based)**: Cloudflare Access handles authentication via email OTP or SSO. Developers run `cloudflared access login preview.internal.example project.example.com` once to get a short-lived JWT for CLI tools (curl, psql).
- **Latency**: Tunnel adds 20-50 ms round-trip vs direct access. Acceptable for QA and internal tools; do not route production customer traffic through tunnels.
- **TCP services**: PostgreSQL and Redis over the tunnel require `cloudflared access tcp` on the client side to create a local loopback proxy: `cloudflared access tcp --hostname db-private.example project.example.com --url localhost:5433`

## Anti-patterns

- Running `cloudflared tunnel run` in a shell without a process supervisor — the tunnel disappears silently on SSH disconnection or OOM and nothing alerts on it
- Routing production user-facing traffic through a Cloudflare Tunnel instead of using Cloudflare's anycast edge directly via Workers or Pages; tunnels are for private/internal access only
- Using `noTLSVerify: true` to silence cert errors on origin connections — use `originServerName` to match the expected SNI, or set up a local CA for internal services
- Sharing one tunnel config across dev/staging/prod environments — each environment needs its own tunnel ID, credentials file, and ingress rules for isolation
- Committing the tunnel credentials JSON (`<UUID>.json`) to source control — it contains a private key and grants full tunnel control; store it in a secrets manager

## Gotchas

- The tunnel credentials JSON is not rotatable without recreating the tunnel; back it up to Vault or AWS Secrets Manager and reference it by path in systemd `EnvironmentFile`
- `cloudflared` v2024+ creates Named Tunnels by default; older docs describe legacy `--hostname` ephemeral tunnels that do not survive restarts and do not appear in `tunnel list`
- DNS CNAMEs created by `tunnel route dns` are always proxied (orange cloud); disabling the proxy proxy breaks resolution because the CNAME target (`cfargotunnel.com`) is only reachable through Cloudflare's network
- The `metrics` listener in `config.yml` exposes connection counts and latency histograms on the host; scrape it with Prometheus using the `cloudflared` job label
- Tunnel connections use QUIC by default (`--protocol quic`); some restrictive egress firewalls block UDP 7844 — fall back with `--protocol http2` if connections stall at startup

## Verification

```bash
# Validate ingress rules without connecting
cloudflared tunnel --config /etc/cloudflared/config.yml ingress validate

# Check active tunnel connections and PoP locations
cloudflared tunnel info example project-runners-prod

# Tail live request logs from the tunnel
cloudflared tunnel tail example project-runners-prod

# Confirm DNS CNAME resolves through Cloudflare
dig +short preview.internal.example project.example.com
# Should return Cloudflare anycast IPs (104.x.x.x or 172.x.x.x)

# Test the protected endpoint with a valid Access token
TOKEN=$(cloudflared access token -app=https://preview.internal.example project.example.com)
curl -H "cf-access-token: $TOKEN" https://preview.internal.example project.example.com/health

# Scrape tunnel metrics
curl -s http://localhost:2000/metrics | grep cloudflared_tunnel
```

## Related

- `documentation/docs/policies/infra/zero-trust-network-access.md`
- `documentation/docs/policies/infra/github-self-hosted-runners.md`
- `documentation/docs/policies/infra/arc-github-runners-k8s.md`
- `documentation/docs/policies/infra/cloudflare-workers-limits-resource-planning.md`
- `documentation/docs/policies/infra/wrangler-deploys.md`
- `documentation/docs/policies/infra/terraform-cloudflare-provider-workers-d1.md`

## Sources

- https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
- https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/get-started/create-local-tunnel/
- https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/private-net/cloudflared/
- https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/self-hosted-apps/
- https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/configure-tunnels/origin-configuration/
