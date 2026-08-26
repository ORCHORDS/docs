# cloudflare-tunnel-private-service-ingress

Expose private services (databases, internal APIs, dev servers) to the internet
or to your Zero Trust network without opening firewall ports, using Cloudflare
Tunnel (cloudflared) as an outbound-only connector.

**Date:** 2026-08-23
**Author:** example.com
**Status:** production

## Symptom / Use-case

You need to reach a service that lives inside a private network:

- Internal API behind a corporate firewall that must be accessible to a Worker
  or to team members on Cloudflare Access
- Local dev server on a laptop that product/QA must preview without a VPN
- Database or Redis on a home server or bare-metal box with no public IP
- SSH jump host accessible via `cloudflared access ssh` without opening port 22

## Context

Cloudflare Tunnel creates an outbound-only encrypted connection from your
infrastructure to Cloudflare's edge. `cloudflared` (the daemon) dials out to
two or more Cloudflare PoPs over QUIC/HTTP/2 — no inbound ports, no firewall
rules, no NAT traversal. Traffic flows:

```
Browser / Worker / Access app
    → Cloudflare edge
        → cloudflared daemon (on your server)
            → private service (localhost:3000, postgres:5432, etc.)
```

Tunnels are defined in a YAML config and registered to your Cloudflare account.
Access policies (Zero Trust → Access) gate who can reach each public hostname
the tunnel serves.

## Installing and authenticating cloudflared

```bash
# macOS
brew install cloudflared

# Linux (Debian/Ubuntu)
curl -L --output cloudflared.deb \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb

# Authenticate to your Cloudflare account
cloudflared tunnel login
# Opens browser → select the zone → cert.pem saved to ~/.cloudflared/
```

## Creating a tunnel and routing hostnames

```bash
# Create the tunnel (stores credentials JSON locally)
cloudflared tunnel create my-tunnel
# → Tunnel credentials written to ~/.cloudflared/<UUID>.json

# Route a hostname through the tunnel
cloudflared tunnel route dns my-tunnel api.internal.example.com
# → Creates a CNAME in your zone pointing to <UUID>.cfargotunnel.com
```

## Writing the tunnel config file

```yaml
# ~/.cloudflared/config.yaml
tunnel: <TUNNEL_UUID>
credentials-file: /path/to/project

ingress:
  # Public hostname → private service
  - hostname: api.internal.example.com
    service: http://localhost:8080

  # SSH access via Access SSH short-lived certs
  - hostname: ssh.internal.example.com
    service: ssh://localhost:22

  # Dev preview — serve a local Vite server
  - hostname: preview.example.com
    service: http://localhost:5173
    originRequest:
      noTLSVerify: false       # set true only for self-signed certs in dev
      connectTimeout: 10s

  # Catch-all: return 404 for unmatched hostnames
  - service: http_status:404
```

## Running the tunnel as a systemd service

```bash
# Install as a system service (Linux)
sudo cloudflared service install
# → Writes /etc/systemd/system/cloudflared.service
# → Reads config from /etc/cloudflared/config.yaml

sudo systemctl enable --now cloudflared
sudo systemctl status cloudflared
```

For Docker environments:

```yaml
# docker-compose.yml
services:
  cloudflared:
    image: cloudflare/cloudflared:latest
    command: tunnel --config /etc/cloudflared/config.yaml run
    volumes:
      - ./cloudflared:/etc/cloudflared:ro
    restart: unless-stopped
    environment:
      - TUNNEL_TOKEN=${TUNNEL_TOKEN}  # alternative: token-based auth (no JSON file)
```

## Token-based auth (CI/CD and containers)

Instead of a credentials JSON file, export a token string — better for secrets
managers and ephemeral environments:

```bash
# Get the tunnel token (treat as a secret — full tunnel credentials)
cloudflared tunnel token my-tunnel
# → outputs a long base64 string

# Run with token (no config file, no credentials file)
cloudflared tunnel run --token $TUNNEL_TOKEN
```

Store the token in a CI secret or Cloudflare Workers Secret:

```bash
npx wrangler secret put TUNNEL_TOKEN
```

## Calling a tunnel-fronted private API from a Worker

The tunnel exposes the private service on a public Cloudflare hostname. A
Worker can `fetch()` it as any other URL. Add an Access Service Token to avoid
needing a browser challenge:

```typescript
// src/index.ts
export interface Env {
  CF_ACCESS_CLIENT_ID: string;     // Cloudflare Access service token ID
  CF_ACCESS_CLIENT_SECRET: string; // Cloudflare Access service token secret
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const upstream = await fetch("https://api.internal.example.com/data", {
      headers: {
        "CF-Access-Client-Id": env.CF_ACCESS_CLIENT_ID,
        "CF-Access-Client-Secret": env.CF_ACCESS_CLIENT_SECRET,
        "Content-Type": "application/json",
      },
    });

    const data = await upstream.json();
    return Response.json(data);
  },
};
```

## Anti-patterns

- **Opening firewall ports "just in case" alongside the tunnel.** The whole
  value of Tunnel is zero inbound exposure. If port 22 or 443 is open externally,
  you've doubled the attack surface. Close the ports.
- **Using `noTLSVerify: true` in production.** Disabling TLS verification
  between cloudflared and the origin defeats transport encryption for that leg.
  Use a valid cert (even a self-signed one you pin) or use `http://` only on
  localhost origins where TLS is not meaningful.
- **Running cloudflared as root.** The daemon only needs network access. Run
  as a dedicated low-privilege user or inside a container with `--read-only`.
- **Storing the credentials JSON or tunnel token in source control.** Either
  value grants full tunnel control. Use a secrets manager, environment variable,
  or Cloudflare Workers Secrets.
- **One tunnel for everything.** Separate tunnels by environment (staging vs.
  production) so a credential leak in staging cannot affect production routing.

## Gotchas

- **Tunnel reconnects are automatic but not instant.** If `cloudflared` restarts,
  in-flight requests fail. For production, run at least two `cloudflared` replicas
  pointing to the same tunnel UUID — Cloudflare load-balances across them and
  retries on disconnect.
- **DNS changes (tunnel route dns) are not instant.** CNAME propagation can take
  up to 5 minutes even with Cloudflare's authoritative DNS. Do not expect
  immediate reachability after `cloudflared tunnel route dns`.
- **Tunnel hostnames must be in a zone you control on the Cloudflare account
  that owns the tunnel.** You cannot tunnel to a hostname in a zone owned by a
  different account.
- **The `ingress` list is matched top-to-bottom; the last rule must be a
  catch-all.** Omitting the catch-all causes `cloudflared` to fail validation
  at startup.
- **Access policies apply per hostname, not per tunnel.** A tunnel can serve
  multiple hostnames each with a different Access policy (or none). Verify each
  hostname's policy independently.
- **`cloudflared` versions matter.** The daemon must be updated regularly;
  very old versions lose protocol support and stop reconnecting. Pin a recent
  stable release in your Dockerfile and update it in your dependency pipeline.

## Verification

```bash
# Confirm the tunnel is connected
cloudflared tunnel info my-tunnel
# → shows "connections" with healthy PoP entries

# Test the public hostname end-to-end
curl -v https://api.internal.example.com/healthz

# Check Access is enforcing auth (should 302 to Access login)
curl -I https://api.internal.example.com/healthz
# → Location: https://yourteam.cloudflareaccess.com/...

# Test with service token
curl -H "CF-Access-Client-Id: $ID" \
     -H "CF-Access-Client-Secret: $SECRET" \
     https://api.internal.example.com/healthz
# → 200 OK from the private service
```

## Related

- `cloudflare/cloudflare-access-zero-trust-service-tokens.md`
- `cloudflare/cloudflare-access-jwt-validation.md`
- `cloudflare/warp-connector-site-to-site-zero-trust.md`
- `cloudflare/zero-trust-access.md`
- Cloudflare Tunnel docs: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
- cloudflared releases: https://github.com/cloudflare/cloudflared/releases

## Sources

- https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/get-started/
- https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/configure-tunnels/
- https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/self-hosted-apps/
