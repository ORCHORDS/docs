# Cloudflare Tunnels Graceful Drain Deploy Pattern

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You are deploying a new version of an origin service running behind a
Cloudflare Tunnel (`cloudflared`). In-flight requests are dropped because the
old `cloudflared` connector is killed before the new one is healthy and before
the load balancer drains existing connections. This causes HTTP 502/504 errors
visible to end users during every deployment window.

## Context

`cloudflared` runs as a long-lived process that multiplexes HTTP/2 connections
to Cloudflare's edge. Each tunnel can have multiple connectors (replicas)
registered under the same Tunnel UUID. Cloudflare's load balancer will route
new requests only to healthy connectors, so the safe pattern is:

1. Start the new connector replica (new binary / new config).
2. Wait for the new connector to appear as `active` in the Tunnel API.
3. Signal the old connector for graceful shutdown — it finishes in-flight
   requests before disconnecting.
4. Verify zero active connections on the old connector before removing it.

---

## 1. Tunnel Connector Inventory

```typescript
// src/tunnel-status.ts
const CF_ACCOUNT  = process.env.CF_ACCOUNT_ID!;
const CF_TOKEN    = process.env.CF_API_TOKEN!;
const TUNNEL_ID   = process.env.TUNNEL_ID!;

interface Connector {
  id          : string;
  created_on  : string;
  conns       : { origin_ip: string; opened_at: string }[];
}

export async function listConnectors(): Promise<Connector[]> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT}`
    + `/tunnels/${TUNNEL_ID}/connections`,
    { headers: { Authorization: `Bearer ${CF_TOKEN}` } }
  );
  const { result } = await res.json<{ result: Connector[] }>();
  return result;
}
```

---

## 2. Start New Connector

```bash
# systemd drop-in for rolling deploy
# /etc/systemd/system/cloudflared-new.service

[Unit]
Description=Cloudflare Tunnel (new slot)
After=network-online.target

[Service]
ExecStart=/usr/bin/cloudflared-next tunnel --config /etc/cloudflared/config.yml run
Restart=on-failure
RestartSec=5s
Environment=TUNNEL_TOKEN=<new-token>

[Install]
WantedBy=multi-user.target
```

```typescript
// scripts/start-new-connector.ts
import { execSync } from "node:child_process";

execSync("systemctl start cloudflared-new.service", { stdio: "inherit" });
console.log("New connector service started — waiting for registration…");
```

---

## 3. Wait for New Connector to Become Active

```typescript
// scripts/wait-for-connector.ts
import { listConnectors } from "../src/tunnel-status";

const TARGET_ORIGIN = process.env.NEW_ORIGIN_IP!; // e.g. "10.0.1.20"
const TIMEOUT_MS    = 60_000;
const POLL_MS       = 3_000;

const deadline = Date.now() + TIMEOUT_MS;

while (Date.now() < deadline) {
  const connectors = await listConnectors();
  const active = connectors.find(c =>
    c.conns.some(conn => conn.origin_ip === TARGET_ORIGIN)
  );

  if (active) {
    console.log(`New connector ${active.id} is active with ${active.conns.length} conns`);
    process.exit(0);
  }

  console.log("Not yet active — polling in 3 s…");
  await new Promise(r => setTimeout(r, POLL_MS));
}

console.error("Timeout: new connector never became active");
process.exit(1);
```

---

## 4. Graceful Drain on Old Connector

```typescript
// scripts/drain-old-connector.ts
import { listConnectors } from "../src/tunnel-status";

const OLD_ORIGIN = process.env.OLD_ORIGIN_IP!;
const DRAIN_MAX  = 30_000; // ms

// Send SIGTERM to cloudflared — it closes new connections but
// finishes in-flight requests before exiting.
import { execSync } from "node:child_process";
execSync("systemctl stop cloudflared-old.service", { stdio: "inherit" });

console.log(`Draining old connector at ${OLD_ORIGIN}…`);
const deadline = Date.now() + DRAIN_MAX;

while (Date.now() < deadline) {
  const connectors = await listConnectors();
  const old = connectors.find(c =>
    c.conns.some(conn => conn.origin_ip === OLD_ORIGIN)
  );

  if (!old || old.conns.length === 0) {
    console.log("Old connector fully drained.");
    process.exit(0);
  }

  console.log(`${old.conns.length} connections still open — waiting…`);
  await new Promise(r => setTimeout(r, 2_000));
}

console.warn("Drain timeout reached — forcing connector removal");
process.exit(0); // non-fatal: Cloudflare will evict stale connectors automatically
```

---

## 5. cloudflared Config for Graceful Shutdown

```yaml
# /etc/cloudflared/config.yml
tunnel: <TUNNEL_UUID>
credentials-file: /etc/cloudflared/credentials.json

# Grace period before forcefully terminating connections
grace-period: 30s

# Keep-alive connections: drain before shutdown
no-autoupdate: true

ingress:
  - hostname: app.example.com
    service: http://localhost:8080
    originRequest:
      connectTimeout: 10s
      tcpKeepAlive: 30s
      noHappyEyeballs: false
  - service: http_status:404
```

---

## 6. Full Deploy Script

```bash
#!/usr/bin/env bash
# scripts/tunnel-rolling-deploy.sh
set -euo pipefail

OLD_ORIGIN_IP="${1:?pass old origin IP}"
NEW_ORIGIN_IP="${2:?pass new origin IP}"

echo "=== Step 1: start new connector ==="
npx tsx scripts/start-new-connector.ts

echo "=== Step 2: wait for new connector to register ==="
NEW_ORIGIN_IP="$NEW_ORIGIN_IP" npx tsx scripts/wait-for-connector.ts

echo "=== Step 3: drain and stop old connector ==="
OLD_ORIGIN_IP="$OLD_ORIGIN_IP" npx tsx scripts/drain-old-connector.ts

echo "=== Step 4: verify single active connector ==="
CONNECTORS=$(curl -s \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/tunnels/$TUNNEL_ID/connections" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  | jq '.result | length')

if [[ "$CONNECTORS" -ne 1 ]]; then
  echo "WARNING: expected 1 connector, found $CONNECTORS"
  exit 1
fi

echo "Deploy complete — tunnel running on single active connector."
```

---

## Anti-patterns

- **`systemctl restart cloudflared`** — kills the old process instantly before
  the new one registers; causes a gap where zero connectors are active and all
  requests 502.
- **Setting `grace-period: 0`** — bypasses in-flight drain entirely; long
  WebSocket and SSE connections drop mid-stream.
- **Not waiting for the new connector** — the swap proceeds before Cloudflare
  routes traffic to it; the old drain window overlaps with zero healthy
  connectors.
- **Using a single connector replica** — one connector means any deploy has a
  window of downtime; always run ≥ 2 connectors per tunnel for HA.

---

## Gotchas

- `cloudflared` registers with Cloudflare's edge within ~5 s under normal
  network conditions, but DNS resolution delays in some cloud VPCs can push
  this to 15–20 s; set polling timeouts accordingly.
- The Tunnel Connections API (`/tunnels/{id}/connections`) reflects the live
  state at the edge, not the local process state; a local `systemctl status`
  showing "active" does not mean the connector is yet registered at the edge.
- `grace-period` in `config.yml` applies only to SIGTERM; SIGKILL bypasses it.
  Ensure your process manager does not send SIGKILL before the grace period
  expires (systemd: set `TimeoutStopSec` > `grace-period`).
- Tunnel tokens are scoped to the tunnel UUID. Rotating the token requires
  updating `credentials-file` and restarting `cloudflared`; the tunnel UUID
  stays the same so no DNS changes are needed.

---

## Verification

```bash
# List active connectors and their open connection counts
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/tunnels/$TUNNEL_ID/connections" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  | jq '.result[] | {id, origin_ip: .conns[0].origin_ip, conns: (.conns | length)}'

# Confirm no 502s in the past 5 minutes via Analytics Engine
# (requires Workers Analytics Engine integration)
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics/graphql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  --data '{"query":"{ viewer { zones(filter:{zoneTag:\"<ZONE>\"}) { httpRequests1mGroups(filter:{datetime_gt:\"...\",clientHTTPStatusCode:502}) { count } } } }"}'
```

---

## Related

- `cloudflare-tunnel-deploy-automation-ci.md`
- `graceful-shutdown-patterns.md`
- `long-lived-connection-rollout-draining.md`
- `database-connection-drain.md`

---

## Sources

- Cloudflare Tunnel run reference: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/configure-tunnels/
- cloudflared `grace-period` option: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/configure-tunnels/cloudflared-parameters/
- Tunnel Connections API: https://developers.cloudflare.com/api/resources/zero_trust/subresources/tunnels/subresources/connections/
