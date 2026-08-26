# WARP Connector — Site-to-Site Zero Trust Networking

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Two private networks (e.g., an AWS VPC and an on-premises data center) need to reach each other's internal services without standing up a traditional VPN or configuring BGP peering. Users authenticated via Cloudflare Access need to reach private RFC 1918 addresses in either site. You want traffic to route through Cloudflare's network rather than a self-managed IPsec tunnel.

## Context

Cloudflare offers two distinct network-connectivity products in the Zero Trust portfolio:

| Product | Purpose | Who uses it |
|---|---|---|
| **Cloudflare Tunnel** (`cloudflared`) | Expose a single service/origin to the internet or Zero Trust users | DevOps teams, app owners |
| **WARP Connector** | Route entire subnets to/from Cloudflare's network | Network engineers, site-to-site |
| **WARP Client** (user device) | Connect end-user devices to Zero Trust private network | End users |

WARP Connector is a lightweight daemon (`warp-svc`) that runs on a Linux host (physical, VM, or container) inside the private network. Once installed, it creates a WireGuard tunnel to Cloudflare's global network and advertises its local subnet CIDRs into the Zero Trust routing table. This allows:

- **Site-to-site**: two WARP Connectors in different networks can reach each other's subnets via Cloudflare
- **WARP users to private networks**: users running the WARP client can reach private IPs behind a WARP Connector
- **Private DNS resolution**: internal DNS lookups route through the connector

No BGP, no IPsec, no public IP required on the connector host.

## Prerequisites

- Cloudflare Zero Trust account (Teams Free or paid)
- A Linux host with kernel ≥ 5.4 (Ubuntu 22.04 LTS recommended)
- The host must have outbound HTTPS (port 443) access to Cloudflare's network
- The host should have a static private IP on the subnet you want to advertise
- The host's IP forwarding must be enabled

## Installation

```bash
# 1. Add Cloudflare's package repository (Ubuntu/Debian)
curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg \
  | sudo gpg --yes --dearmor --output /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg

echo "deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] \
  https://pkg.cloudflareclient.com/ $(lsb_release -cs) main" \
  | sudo tee /etc/apt/sources.list.d/cloudflare-client.list

sudo apt-get update && sudo apt-get install -y cloudflare-warp

# 2. Enable IP forwarding (required for routing traffic to other hosts in the subnet)
sudo sysctl -w net.ipv4.ip_forward=1
sudo sysctl -w net.ipv6.conf.all.forwarding=1

# Persist across reboots
echo "net.ipv4.ip_forward = 1" | sudo tee -a /etc/sysctl.d/99-warp-connector.conf
echo "net.ipv6.conf.all.forwarding = 1" | sudo tee -a /etc/sysctl.d/99-warp-connector.conf
sudo sysctl -p /etc/sysctl.d/99-warp-connector.conf
```

## Registering the WARP Connector

```bash
# 3. Register as a connector (not a user device)
#    --enrollment-token is obtained from Zero Trust dashboard:
#    Settings → WARP Client → Device enrollment → Create a token
warp-cli --accept-tos connector new

# Or enroll with a token from an MDM-style flow
warp-cli --accept-tos register --connector \
  --enrollment-token "eyJhbGciOiJFUzI1NiJ9..."

# 4. Connect the tunnel
warp-cli connect

# 5. Verify connection status
warp-cli status
# Expected: Status update: Connected
```

## Advertising Subnet CIDRs

After connecting, register the subnets this connector should route in the Zero Trust dashboard:

**Settings → Networks → Tunnels → [Your Connector] → Private Networks → Add a network**

Or via the API:

```bash
# Get the connector's virtual network (vnet) ID
curl -s "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/teamnet/virtual_networks" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '.result[] | {id, name}'

# Register the private subnet 10.0.0.0/8 via the connector's virtual network
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/teamnet/routes" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "network": "10.100.0.0/24",
    "virtual_network_id": "VNET_ID_HERE",
    "comment": "Production VPC subnet via WARP Connector"
  }'
```

## Split Tunnel Configuration (Exclude or Include Mode)

WARP client devices determine which traffic routes through Zero Trust via Split Tunnel config. For WARP Connector hosts, split tunnels are set on the device profile in the dashboard, not on the connector itself.

Two modes:
- **Exclude mode** (default): all traffic goes through WARP *except* explicitly excluded CIDRs/domains
- **Include mode**: only explicitly listed CIDRs/domains go through WARP

For a connector that should only tunnel private subnets (not internet traffic):

```
# Dashboard: Settings → WARP Client → Device settings → [Profile] → Split Tunnels
# Mode: Include
# Include these CIDRs:
# 10.0.0.0/8
# 172.16.0.0/12
# 192.168.0.0/16
# fd00::/8   (IPv6 ULA)
```

## Site-to-Site: Two WARP Connectors

```
[Site A: 10.100.0.0/24]          [Cloudflare Network]       [Site B: 10.200.0.0/24]
  WARP Connector A     ←— WireGuard —→  Routing   ←— WireGuard —→  WARP Connector B
  (host: 10.100.0.5)                    Table                        (host: 10.200.0.5)
```

Configuration steps:
1. Install WARP Connector on a host in each site
2. Register both connectors in the same Zero Trust account
3. Create separate Virtual Networks for each site in Teams dashboard, or use the default vnet
4. Add the private route `10.100.0.0/24` pointing to Connector A's vnet
5. Add the private route `10.200.0.0/24` pointing to Connector B's vnet
6. Enable **Gateway** → **Network** → **Private Network Routing** so Zero Trust knows to forward traffic between vnets

Verify from Site A:
```bash
ping 10.200.0.10    # a host in Site B
curl http://10.200.0.10:8080/health
```

## Private DNS Resolution

WARP Connector sites can participate in private DNS. Register a Gateway DNS Location pointing to the connector's virtual network:

```
# Dashboard: Gateway → DNS Locations → Add a location
# Type: IPv4 (use the connector host's Cloudflare-assigned internal IP)
# Associate with virtual network: [Site A vnet]
```

Then add DNS policies to resolve internal domains:

```
# Gateway → DNS → Policies → Create a policy
# Selector: DNS Domain → matches "internal.corp"
# Action: Override → IP: 10.100.0.53   (internal DNS resolver at Site A)
```

## Terraform Configuration

```hcl
resource "cloudflare_tunnel_virtual_network" "site_a" {
  account_id = var.account_id
  name       = "site-a-vpc"
  comment    = "AWS us-east-1 VPC"
}

resource "cloudflare_tunnel_virtual_network" "site_b" {
  account_id = var.account_id
  name       = "site-b-dc"
  comment    = "On-premises data center"
}

resource "cloudflare_tunnel_route" "site_a_subnet" {
  account_id         = var.account_id
  virtual_network_id = cloudflare_tunnel_virtual_network.site_a.id
  network            = "10.100.0.0/24"
  comment            = "Site A production subnet"
}

resource "cloudflare_tunnel_route" "site_b_subnet" {
  account_id         = var.account_id
  virtual_network_id = cloudflare_tunnel_virtual_network.site_b.id
  network            = "10.200.0.0/24"
  comment            = "Site B data center subnet"
}
```

The WARP Connector daemon itself is enrolled out-of-band (not via Terraform). Manage the connector hosts with your config management tooling (Ansible, Chef, etc.).

## Anti-patterns

- **Running WARP Connector on a host without IP forwarding** — the connector can reach the remote network but hosts behind it cannot. IP forwarding is mandatory on the connector host, and routing tables on adjacent hosts must point to the connector's IP for non-local subnets.
- **Using WARP Connector as a replacement for Cloudflare Tunnel for app exposure** — Tunnel is the right tool for exposing a specific service; WARP Connector is for subnet-level routing. Using WARP Connector to expose a web app adds unnecessary routing complexity.
- **Running the connector as root continuously** — `warp-svc` should run as a systemd service under a dedicated non-root user with the `CAP_NET_ADMIN` capability.
- **Overlapping CIDRs across virtual networks** — if both Site A and Site B use `10.0.0.0/8`, Cloudflare's routing table cannot disambiguate. Use non-overlapping CIDRs or separate virtual networks with explicit subnet masks.
- **Not monitoring the connector's health** — connectors do not self-heal from kernel routing table corruption. Monitor `warp-cli status` output via a cron or monitoring agent.

## Gotchas

- WARP Connector requires the **cloudflare-warp** package, not `cloudflared`. They are separate binaries with different architectures.
- On AWS, the EC2 instance running the connector must have the **source/destination check disabled** at the network interface level (EC2 → Network Interfaces → Change Source/Dest Check).
- WARP Connector enrollment tokens expire after 30 days by default. Rotate them before re-provisioning hosts.
- `warp-cli` commands require root or the `warp` group on the host. Add your deployment user: `usermod -aG warp deploy`.
- The WARP Connector daemon does not support FreeBSD or macOS; it is Linux-only.
- When using Gateway DNS policies alongside a WARP Connector, ensure the Gateway DNS location's source IP is in the allowed IP range for the associated virtual network to avoid DNS resolution failures.

## Verification

```bash
# Connector status
warp-cli status

# Check registered virtual networks
curl -s "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/teamnet/virtual_networks" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[] | {id, name}'

# Check registered routes
curl -s "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/teamnet/routes" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[] | {network, comment}'

# From a WARP client device, verify connectivity to the private subnet
warp-cli tunnel stats      # on end-user device — see bytes in/out
ping 10.100.0.10           # target host in the remote subnet
```

## Related

- `cloudflare-access-zero-trust-service-tokens.md` — machine-to-machine auth for services exposed behind Access
- `zero-trust-device-posture.md` — posture checks that gate WARP client access to connectors
- `zero-trust-warp-client-policies.md` — end-user WARP client device profiles and split tunnel config
- `cloudflare-dns-workers-custom-domains.md` — DNS routing patterns within the Zero Trust stack

## Sources

- https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/private-net/warp-connector/
- https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/private-net/cloudflared/
- https://developers.cloudflare.com/api/resources/zero_trust/subresources/networks/subresources/virtual_networks/
- https://developers.cloudflare.com/api/resources/zero_trust/subresources/networks/subresources/routes/
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/tunnel_virtual_network
