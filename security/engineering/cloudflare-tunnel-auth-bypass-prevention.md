# Cloudflare Tunnel Authentication Bypass Prevention

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
A Cloudflare Tunnel (`cloudflared`) that routes traffic to an internal service can be bypassed if the tunnel is misconfigured to serve the origin directly without Cloudflare Access protection, if the `cloudflared` daemon allows unauthenticated ingress rules, or if internal services trust headers forwarded through the tunnel without validating their origin.

## Context
Cloudflare Tunnel creates an outbound-only connection from an internal host to Cloudflare's network, enabling traffic to reach an internal service without opening inbound firewall ports. The tunnel is secured by pairing it with Cloudflare Access—but if the Access application is not configured, or if the `config.yml` ingress rules allow public traffic, the service is publicly reachable with no authentication. Additionally, services behind the tunnel often trust headers like `CF-Access-Authenticated-User-Email` without verifying the cryptographic JWT that backs them.

---

## Section 1 — Bind Every Tunnel Hostname to a Cloudflare Access Application

Every hostname routed through a Tunnel must have a corresponding Access application with at least one `Allow` policy. An ingress rule with no Access application is publicly reachable.

```yaml
# config.yml for cloudflared — annotated for security
tunnel: <your-tunnel-id>
credentials-file: /etc/cloudflared/<your-tunnel-id>.json

ingress:
  # Each hostname MUST have a corresponding Access application in the dashboard
  - hostname: internal-api.example.com
    service: http://localhost:8080
    originRequest:
      # Enforce that the connection to the local service uses TLS if possible
      noTLSVerify: false
      # Set a conservative connect timeout
      connectTimeout: 10s
      # Do not allow HTTP/2 upgrade unless your origin supports it correctly
      http2Origin: false

  # CATCH-ALL: deny all unmatched traffic — never route catch-all to a real service
  - service: http_status:404
```

The dashboard counterpart — creating the Access application — must be done separately. Verify with:

```bash
# List all ingress rules and confirm each has an Access application
cloudflared tunnel ingress validate
```

---

## Section 2 — Validate CF-Access-Jwt-Assertion at the Origin Service

The origin service behind the tunnel MUST validate the `CF-Access-Jwt-Assertion` header cryptographically, not merely check for its presence. An attacker who reaches the `cloudflared` daemon's local port (e.g., via SSRF from another internal service) can fabricate any header value.

```typescript
// Express.js origin service example (Node.js behind the tunnel)
import express from 'express';
import { createRemoteJWKSet, jwtVerify } from 'jose';

const app = express();

const TEAM_DOMAIN = process.env.CF_ACCESS_TEAM_DOMAIN!;
const AUD = process.env.CF_ACCESS_AUD!;
const JWKS = createRemoteJWKSet(
  new URL(`https://${TEAM_DOMAIN}/cdn-cgi/access/certs`)
);

async function validateAccessJWT(req: express.Request, res: express.Response, next: express.NextFunction) {
  const token = req.headers['cf-access-jwt-assertion'];
  if (!token || typeof token !== 'string') {
    res.status(401).json({ error: 'Missing Access JWT' });
    return;
  }

  try {
    const { payload } = await jwtVerify(token, JWKS, {
      audience: AUD,
      issuer: `https://${TEAM_DOMAIN}`,
    });

    // Attach verified identity for downstream handlers
    (req as any).accessEmail = payload.email;
    (req as any).accessSub = payload.sub;
    next();
  } catch (err) {
    res.status(403).json({ error: 'Invalid or expired Access JWT' });
  }
}

app.use(validateAccessJWT);

app.get('/api/data', (req, res) => {
  res.json({ user: (req as any).accessEmail });
});

app.listen(8080, '127.0.0.1'); // bind to localhost only, not 0.0.0.0
```

Binding to `127.0.0.1` (not `0.0.0.0`) ensures the origin service is unreachable except via the `cloudflared` daemon on the same host.

---

## Section 3 — Restrict the cloudflared Service Account

The `cloudflared` process and credentials file should be owned by a dedicated low-privilege user. The credentials file (JSON containing the tunnel secret) must have strict file permissions.

```bash
# Create a dedicated user for cloudflared
useradd -r -s /sbin/nologin cloudflared

# Restrict credentials file
install -o cloudflared -g cloudflared -m 600 \
  /tmp/<tunnel-id>.json /etc/cloudflared/<tunnel-id>.json

# Run cloudflared as the dedicated user via systemd
cat > /etc/systemd/system/cloudflared.service <<'EOF'
[Unit]
Description=Cloudflare Tunnel
After=network.target

[Service]
User=cloudflared
Group=cloudflared
ExecStart=/usr/local/bin/cloudflared tunnel --config /etc/cloudflared/config.yml run
Restart=on-failure
RestartSec=5s
# Harden the service
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/var/lib/cloudflared

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now cloudflared
```

---

## Section 4 — Monitor for Tunnel Reconnection and Certificate Rotation Events

A tunnel that silently reconnects under a different tunnel ID (e.g., due to credential rotation or an attacker re-registering the tunnel) bypasses the Access policies bound to the original hostname. Alert on tunnel ID changes.

```typescript
// Workers Cron Job: verify tunnel status matches expected tunnel ID
interface Env {
  CF_API_TOKEN: string;
  CF_ACCOUNT_ID: string;
  EXPECTED_TUNNEL_ID: string;
  EXPECTED_TUNNEL_HOSTNAME: string;
  ALERT_WEBHOOK_URL: string;
}

async function auditTunnelConfig(env: Env): Promise<void> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/cfd_tunnel`,
    { headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` } }
  );
  const { result: tunnels } = (await res.json()) as { result: TunnelRecord[] };

  for (const tunnel of tunnels) {
    if (tunnel.status === 'active' && tunnel.id !== env.EXPECTED_TUNNEL_ID) {
      await fetch(env.ALERT_WEBHOOK_URL, {
        method: 'POST',
        body: JSON.stringify({
          alert: 'Unexpected active tunnel detected',
          tunnelId: tunnel.id,
          name: tunnel.name,
          createdAt: tunnel.created_at,
        }),
      });
    }
  }

  // Verify the expected tunnel is still bound to the expected hostname
  const routeRes = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/cfd_tunnel/${env.EXPECTED_TUNNEL_ID}/configurations`,
    { headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` } }
  );
  const { result: config } = (await routeRes.json()) as { result: TunnelConfig };
  const hostnames = config.config.ingress.map((r: IngressRule) => r.hostname);
  if (!hostnames.includes(env.EXPECTED_TUNNEL_HOSTNAME)) {
    await fetch(env.ALERT_WEBHOOK_URL, {
      method: 'POST',
      body: JSON.stringify({
        alert: 'Expected hostname missing from tunnel ingress',
        expected: env.EXPECTED_TUNNEL_HOSTNAME,
        actual: hostnames,
      }),
    });
  }
}

interface TunnelRecord { id: string; name: string; status: string; created_at: string; }
interface IngressRule { hostname?: string; service: string; }
interface TunnelConfig { config: { ingress: IngressRule[] }; }

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await auditTunnelConfig(env);
  }
};
```

---

## Anti-patterns

- Having a catch-all ingress rule in `config.yml` that routes to a real service — this bypasses Access for any unrecognized hostname.
- Trusting `CF-Access-Authenticated-User-Email` without validating the corresponding JWT — this header can be set by any caller that reaches the `cloudflared` local port.
- Running `cloudflared` as root or as the same user as the origin application — a compromise of the application can then modify the tunnel config.
- Using `noTLSVerify: true` in the `originRequest` block — this disables certificate validation for connections from `cloudflared` to the local service, enabling MITM if the local host is compromised.
- Configuring the origin service to listen on `0.0.0.0` — this allows lateral-movement access from any other process on the host, not just `cloudflared`.
- Not associating a Cloudflare Access application with the tunnel hostname before the tunnel goes live — there is a window where the service is publicly accessible.

---

## Gotchas

- Cloudflare Access and Cloudflare Tunnel are separate products. Creating a Tunnel does not automatically create an Access application. You must explicitly create the Access application and set its subdomain to match the tunnel's public hostname.
- If the Access application is set to "Bypass" for certain IP ranges (e.g., office IPs), those bypasses apply to tunnel-routed traffic as well. Review bypass rules carefully.
- The `cloudflared` credentials JSON file contains a certificate and private key that authenticate the tunnel to Cloudflare. If this file is leaked, an attacker can register a new tunnel under your account. Rotate tunnel credentials via `cloudflared tunnel rotate-secret`.
- Tunnel ingress rules are matched top-to-bottom; a wildcard rule (e.g., `hostname: "*.internal.example.com"`) placed above a more specific rule will shadow the specific rule. Review ingress rule order.
- `cloudflared tunnel ingress validate` only validates the config.yml syntax and routing logic; it does not verify that Access applications exist for each hostname.
- Short-lived tunnels (created via `cloudflared tunnel create` during CI) should be deleted with `cloudflared tunnel delete` after use; stale tunnels remain registered in your account and can be re-activated.

---

## Verification

1. Access the tunnel public hostname directly in a browser with no Access session and confirm you are redirected to the Access login page.
2. Attempt to reach the origin service's local port from another process on the same host and confirm it is refused (if bound to `127.0.0.1` correctly).
3. Send a request to the tunnel hostname with a fabricated `CF-Access-Jwt-Assertion: invalid` header and confirm the origin service returns `403`.
4. Run the scheduled audit Worker and confirm it correctly identifies the expected tunnel and hostname.
5. Review the Cloudflare dashboard under **Zero Trust → Networks → Tunnels** and confirm each active tunnel has a corresponding Access application.

---

## Related

- `cloudflare-access-bypass-prevention.md`
- `cloudflare-access-jwt-assertion-validation.md`
- `cloudflare-zero-trust-mtls-service-auth.md`
- `zero-trust-network-architecture-ztna.md`
- `service-binding-zero-trust-workers.md`

---

## Sources

- https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
- https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/configure-tunnels/local-management/configuration-file/
- https://developers.cloudflare.com/cloudflare-one/identity/authorization-cookie/validating-json/
- https://developers.cloudflare.com/api/resources/zero_trust/subresources/tunnels/
- https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/configure-tunnels/tunnel-permissions/
