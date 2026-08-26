# bgp-routing-basics

**Issue:** BGP fundamentals relevant to cloud networking, Direct Connect, and multi-homed setups
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
AWS Direct Connect BGP session flapping, route leaks, or incorrect traffic engineering between on-prem and cloud.

## Pattern / Solution
Key BGP concepts for cloud operators:
```
AS (Autonomous System): A network with a unique ASN. AWS has multiple ASNs per region.
eBGP: BGP between different ASes (on-prem ↔ AWS)
iBGP: BGP within same AS

Route preference (highest wins):
1. Weight (Cisco proprietary, local to router)
2. Local Preference (iBGP scope)
3. AS Path length (shorter = preferred)
4. Origin (IGP < EGP < incomplete)
5. MED (Multi-Exit Discriminator — hint to peer)
```

AWS Direct Connect BGP config:
```
Amazon side ASN: 64512 (private) or 7224 (public)
Your ASN: any private ASN (64512–65534) for private VIF

BGP MD5 auth — configure matching key on both sides:
  aws dx create-bgp-peer --virtual-interface-id dxvif-xxx \
    --bgp-auth-key "s3cur3k3y"
```

Influencing inbound traffic to your on-prem (MED):
```
# Prefer primary path: advertise lower MED on primary DX
# Prefer secondary path: advertise higher MED (or AS-PATH prepend)
neighbor 169.254.0.1 route-map SET-MED out
route-map SET-MED permit 10
  set metric 100   # lower = preferred
```

BFD (Bidirectional Forwarding Detection) for fast failure detection:
```
# AWS DX supports BFD — enable on your router
neighbor 169.254.0.1 fall-over bfd
bfd interval 300 min_rx 300 multiplier 3
```

## Gotchas
- Direct Connect does not failover automatically to VPN unless you configure BGP priorities correctly
- AWS advertises more specific routes over VPN to make DX preferred — verify this matches your intent
- BGP session goes down if MD5 key mismatches even by whitespace — copy carefully
- Transit Gateway route tables are separate from BGP — imported routes must be propagated to the right TGW route table

## Related
- `global-load-balancing-anycast.md`
- `vpc-subnet-design.md`
- `network-bandwidth-optimization.md`
