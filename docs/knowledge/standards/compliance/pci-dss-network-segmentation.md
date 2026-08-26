# pci-dss-network-segmentation

**Issue:** Implementing PCI DSS network segmentation to reduce cardholder data environment (CDE) scope
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Without proper segmentation, every system becomes part of the CDE, dramatically increasing compliance scope and cost. Proper segmentation isolates cardholder data and reduces systems in scope by 90%+ in typical environments.

## Pattern / Solution
CDE segmentation approach:

Network zones:
```
Internet
    |
[WAF/Load Balancer] — DMZ
    |
[App Servers] — Application Zone (in-scope if they touch PANs)
    |
[Tokenization Service] — isolates raw PANs
    |
[Payment Processor] — out-of-scope if outsourced
    |
[Database] — CDE (if raw PANs stored)
```

Firewall rules (Req 1):
- Default deny; explicit allow rules only
- No direct connectivity between internet and CDE
- All inbound/outbound CDE traffic documented and reviewed every 6 months
- Stateful inspection; no split tunneling from CDE to internet

Segmentation controls:
- Separate VPCs or VLANs for CDE systems
- Network ACLs + security groups (defense in depth)
- Micro-segmentation for east-west traffic within CDE
- No CDE systems on shared Wi-Fi or unmanaged networks

Segmentation test (annually or after changes):
- Penetration test specifically validates segmentation
- QSA must confirm that out-of-scope systems cannot reach CDE
- Test from all network zones (internet, corporate, partner networks)

Tokenization to reduce scope:
- Replace PANs with tokens at point of entry
- Only tokenization service handles raw PANs
- Rest of application uses tokens — no CDE scope

## Gotchas
- Developers with VPN access to both CDE and internet are a segmentation failure
- Cloud security groups alone are not sufficient — QSAs require additional controls
- Logging and monitoring systems that collect CDE logs are in-scope even if they do not process PANs
- Annual segmentation pen test is a hard requirement in PCI DSS 4.0

## Related
- `pci-dss-tokenization-patterns.md`
- `pci-dss-v4.md`
