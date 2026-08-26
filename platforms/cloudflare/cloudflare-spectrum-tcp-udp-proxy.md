# Cloudflare Spectrum for TCP/UDP Proxy

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

You run a game server on UDP port 7777, an SSH jump host on port 22, a MQTT broker on TCP port 1883, or a custom binary protocol on an arbitrary port. You want Cloudflare's DDoS protection and Anycast network in front of these services without running them through an HTTP reverse proxy. Spectrum lets you proxy any TCP or UDP application through Cloudflare's edge on non-standard ports.

---

## Context

Cloudflare Spectrum is available on the **Pro plan and above** (TCP only) and the **Business / Enterprise plan** (TCP + UDP). It works at the network layer (L4), not the application layer (L7), so Cloudflare does not inspect or modify the protocol payload — it just proxies the connection with DDoS scrubbing and Anycast routing.

Key differences from a standard HTTP proxy (orange-cloud DNS):

| Feature | HTTP (orange cloud) | Spectrum (L4 proxy) |
|---------|--------------------|--------------------|
| Protocol | HTTP/HTTPS only | Any TCP/UDP |
| Port | 80, 443, 8080, 8443, … | 1–65535 (any) |
| WAF / Firewall Rules | Yes | No (IP Firewall only) |
| TLS termination | Yes (Cloudflare cert) | Optional (pass-through or terminate) |
| Client IP visibility | CF-Connecting-IP header | PROXY protocol header or direct |
| Plan requirement | Free | Pro (TCP), Business/Enterprise (UDP) |
| Analytics | Full HTTP analytics | Spectrum-specific analytics |

---

## Creating a Spectrum Application via Dashboard

```
Cloudflare Dashboard → [zone] → Spectrum → Create Application

Protocol:         TCP (or UDP on Business+)
Port or range:    22         (single port)
                  27000-27020 (port range — Enterprise only)
Edge IP:          Shared (Anycast pool) or Dedicated IP
Origin:
  - Type: Server
  - Value: origin.example.com  (or 203.0.113.10)
  - Port: 22

TLS:              Off  (pass-through — SSH handles its own encryption)
                  On   (Cloudflare terminates TLS — use for non-TLS services
                         like plain MQTT, raw TCP)
```

---

## Creating a Spectrum Application via API

```bash
# TCP: proxy SSH on port 22
curl -X POST \
  "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/spectrum/apps" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "protocol": "tcp/22",
    "dns": {
      "type": "CNAME",
      "name": "ssh.example.com"
    },
    "origin_dns": {
      "name": "origin.example.com",
      "ttl": 1200
    },
    "origin_port": 22,
    "ip_firewall": true,
    "proxy_protocol": "v1",
    "tls": "off",
    "edge_ips": {
      "type": "dynamic",
      "connectivity": "all"
    }
  }'

# UDP: proxy a game server on port 7777 (Business+ plan)
curl -X POST \
  "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/spectrum/apps" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "protocol": "udp/7777",
    "dns": {
      "type": "CNAME",
      "name": "game.example.com"
    },
    "origin_dns": {
      "name": "gameserver.example.com",
      "ttl": 300
    },
    "origin_port": 7777,
    "ip_firewall": true,
    "proxy_protocol": "off",
    "edge_ips": {
      "type": "dynamic",
      "connectivity": "ipv4"
    }
  }'
```

---

## PROXY Protocol for Real Client IP

By default, your origin sees the Cloudflare edge IP as the connecting client, not the real client IP. Enable **PROXY protocol** to prepend a header that carries the original client IP and port. Two versions:

- **v1** — human-readable ASCII header. Compatible with HAProxy, nginx (`proxy_protocol on`), OpenSSH, many servers.
- **v2** — binary header. Faster, supports TLV extensions for connection identity. Required for some Enterprise features.

### Nginx with PROXY protocol v1

```nginx
# /etc/nginx/nginx.conf
stream {
    log_format proxy '$remote_addr [$time_local] '
                     '$protocol $status $bytes_sent $bytes_received '
                     '$session_time';

    server {
        listen 22 proxy_protocol;   # <-- enable PROXY protocol parsing

        set_real_ip_from  173.245.48.0/20;  # Cloudflare IP ranges
        set_real_ip_from  103.21.244.0/22;
        set_real_ip_from  103.22.200.0/22;
        set_real_ip_from  103.31.4.0/22;
        set_real_ip_from  141.101.64.0/18;
        set_real_ip_from  108.162.192.0/18;
        set_real_ip_from  190.93.240.0/20;
        set_real_ip_from  188.114.96.0/20;
        set_real_ip_from  197.234.240.0/22;
        set_real_ip_from  198.41.128.0/17;
        set_real_ip_from  162.158.0.0/15;
        set_real_ip_from  104.16.0.0/13;
        set_real_ip_from  104.24.0.0/14;
        set_real_ip_from  172.64.0.0/13;
        set_real_ip_from  131.0.72.0/22;

        proxy_pass 127.0.0.1:22_internal;
        access_log /var/log/nginx/spectrum-ssh.log proxy;
    }

    server {
        # Internal SSH daemon listens here — not exposed to public
        listen 22_internal;
        proxy_pass unix:/var/run/sshd.sock;
    }
}
```

### Node.js TCP server reading PROXY protocol v1

```typescript
// server.ts — reads PROXY protocol v1 header from Spectrum
import net from "net";

const server = net.createServer((socket) => {
  let headerRead = false;
  let clientIp = socket.remoteAddress;
  let clientPort = socket.remotePort;
  let buffer = "";

  socket.setEncoding("utf8");
  socket.once("data", (chunk: string) => {
    if (!headerRead && chunk.startsWith("PROXY ")) {
      // Format: PROXY TCP4 <client-ip> <proxy-ip> <client-port> <proxy-port>\r\n
      const headerEnd = chunk.indexOf("\r\n");
      const header = chunk.slice(0, headerEnd);
      const parts = header.split(" ");
      clientIp = parts[2];
      clientPort = parseInt(parts[4], 10);
      buffer = chunk.slice(headerEnd + 2); // remaining application data
      headerRead = true;
    } else {
      buffer = chunk;
      headerRead = true;
    }

    console.log(`Connection from real IP: ${clientIp}:${clientPort}`);
    // Process buffer + subsequent data
    socket.on("data", handleData.bind(null, socket));
    if (buffer.length > 0) handleData(socket, buffer);
  });
});

function handleData(socket: net.Socket, data: string): void {
  // Your protocol handler
  socket.write(`Echo: ${data}`);
}

server.listen(7777, "0.0.0.0");
```

---

## IP Firewall Rules for Spectrum

Spectrum applications respect **IP Access Rules** (not WAF rules, which are HTTP-only). Create rules via API:

```bash
# Block a known malicious IP from reaching your Spectrum app
curl -X POST \
  "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/firewall/access_rules/rules" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "block",
    "configuration": {
      "target": "ip",
      "value": "198.51.100.1"
    },
    "notes": "Known DDoS source — blocked 2026-08"
  }'

# Allow only your office range to reach SSH spectrum app
# (Challenge or block everything else via a separate rule + a wider CIDR)
curl -X POST \
  "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/firewall/access_rules/rules" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "whitelist",
    "configuration": {
      "target": "ip_range",
      "value": "203.0.113.0/24"
    },
    "notes": "Office CIDR — allow SSH"
  }'
```

---

## Terraform Configuration

```hcl
# spectrum.tf
resource "cloudflare_spectrum_application" "ssh" {
  zone_id  = var.zone_id
  protocol = "tcp/22"

  dns {
    type = "CNAME"
    name = "ssh.${var.domain}"
  }

  origin_dns {
    name = "origin.${var.domain}"
    ttl  = 1200
  }

  origin_port    = 22
  ip_firewall    = true
  proxy_protocol = "v1"
  tls            = "off"

  edge_ips {
    type         = "dynamic"
    connectivity = "all"
  }
}

resource "cloudflare_spectrum_application" "mqtt" {
  zone_id  = var.zone_id
  protocol = "tcp/1883"

  dns {
    type = "CNAME"
    name = "mqtt.${var.domain}"
  }

  origin_dns {
    name = "mqtt-broker.${var.domain}"
    ttl  = 300
  }

  origin_port    = 1883
  ip_firewall    = true
  proxy_protocol = "off"   # MQTT brokers often don't support PROXY protocol
  tls            = "on"    # Terminate TLS at Cloudflare edge for plain MQTT
}
```

---

## Monitoring Spectrum Traffic

Spectrum has its own analytics endpoint separate from the zone's HTTP analytics:

```bash
# GraphQL query for Spectrum throughput (last 24 hours)
curl "https://api.cloudflare.com/client/v4/graphql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "query { viewer { zones(filter: {zoneTag: \"'"${CF_ZONE_ID}"'\"}) { spectrumAnalyticsByAdaptiveGroups(limit: 100, filter: { datetime_gt: \"'"$(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ)"'\" }, orderBy: [datetime_ASC]) { dimensions { applicationTag datetime } sum { bytesIngress bytesEgress } } } } }"
  }' | jq '.data.viewer.zones[0].spectrumAnalyticsByAdaptiveGroups'
```

---

## Anti-patterns

- **Using Spectrum for HTTP/HTTPS traffic.** HTTP traffic belongs on the standard orange-cloud proxy which gives you WAF, caching, and Page Rules. Spectrum on port 80/443 bypasses all of those features and costs more.
- **Enabling PROXY protocol without the origin server supporting it.** If your origin server does not parse the `PROXY` header, it will treat it as application data and break the connection. Test with `nc -l 22` and inspect raw bytes before enabling.
- **Relying on Spectrum UDP for latency-critical games without testing jitter.** Spectrum UDP is a stateless proxy. Cloudflare does not guarantee packet ordering for UDP. High-frequency game state updates (>30 pps) with strict ordering requirements may perform worse through Spectrum than direct.
- **Using shared Anycast IPs for Spectrum when you need source IP allowlisting.** Shared IPs are pooled — other Cloudflare customers share them. Use **Dedicated Egress IPs** (Enterprise) when your origin's firewall needs to allowlist the Cloudflare source IP.

---

## Gotchas

1. **Spectrum DNS records are always proxied.** You cannot set a Spectrum DNS record to DNS-only (grey cloud). The orange cloud is mandatory because Spectrum is the proxy.
2. **Port ranges require Enterprise.** Pro and Business can only proxy a single port per application. Port ranges (e.g., `27000-27030` for Source game servers) require Enterprise.
3. **UDP and IP Firewall.** IP Firewall rules block connections at the edge before packets reach the origin. For UDP, "blocking" means Cloudflare drops the packets — the client will not receive a reset or ICMP unreachable; it will just time out.
4. **TLS termination on Spectrum requires a certificate on the zone.** If you enable `tls: on`, Cloudflare terminates TLS using the zone's edge certificate (managed or uploaded). The origin connection after termination is unencrypted unless you also configure origin TLS.
5. **Spectrum does not support WebSockets.** If your TCP service upgrades to WebSocket after an HTTP handshake, use the standard HTTP proxy with Workers for WebSocket handling instead.
6. **PROXY protocol v2 binary header is not human-readable.** Test your origin's parsing with a dedicated harness before going to production — a stray `\r\n` assumption breaks v2.

---

## Verification

```bash
# Confirm the Spectrum application is created
curl "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/spectrum/apps" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[] | {id, protocol, dns}'

# Test TCP connection to Spectrum endpoint
nc -zv ssh.example.com 22
# Expected: Connection to ssh.example.com 22 port [tcp/ssh] succeeded!

# Test SSH through Spectrum (should see Cloudflare Anycast IP in SSH server logs)
ssh -v user@ssh.example.com 2>&1 | grep "Connecting to"

# Verify PROXY protocol header is received by a debug listener
nc -l 22 -v  # on origin; connect through Spectrum and watch for "PROXY TCP4 ..."
```

---

## Related

- `magic-transit-spectrum-network-edge.md` — Magic Transit (L3) vs. Spectrum (L4) decision guide
- `under-attack-mode-ddos-runbook.md` — Layer 3/4 DDoS response alongside Spectrum
- `workers-websocket-upgrade.md` — WebSocket proxying via HTTP (for L7 WebSocket traffic)
- `cloudflare-terraform-provider-iac.md` — Terraform provider setup and authentication
- `load-balancing-workers-health-checks.md` — combining Spectrum with load balancers for HA

---

## Sources

- Cloudflare Spectrum documentation: https://developers.cloudflare.com/spectrum/
- Spectrum API reference: https://developers.cloudflare.com/api/operations/spectrum-applications-list-spectrum-applications
- PROXY protocol specification: https://www.haproxy.org/download/1.8/doc/proxy-protocol.txt
- Spectrum Analytics GraphQL: https://developers.cloudflare.com/analytics/graphql-api/features/data-sets/spectrum/
- Terraform cloudflare_spectrum_application: https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/spectrum_application
