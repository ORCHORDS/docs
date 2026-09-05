---
title: ISO/IEC 27033 Network Security Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: ISO/IEC 27033 series — Network Security; ISO/IEC 27033-1:2015 (Overview and concepts); ISO/IEC 27033-2:2022 (Guidelines for the design and implementation of network security); ISO/IEC 27033-3:2022 (Reference networking scenarios); ISO/IEC 27033-4:2014 (Securing communications between networks using security gateways); ISO/IEC 27033-5:2024 (Securing communications across networks using virtual private networks); ISO/IEC 27033-6:2016 (Securing wireless IP network access); ISO/IEC 27033-7:2024 (Guidelines for network virtualization); https://www.iso.org/standard/63461.html
---

# ISO/IEC 27033 Network Security Governance

## Scope

This card governs how `orchords-docs` evaluates network security against the ISO/IEC 27033 series. It is the reference input for any KB card that describes a network architecture, security gateway, VPN, wireless network, or network virtualization.

## Why this card exists

ISO/IEC 27033 is the network-security overlay of ISO/IEC 27002. It prescribes design, implementation, and operational security for networks. Without an explicit card, the KB cites network security practices that do not survive a network-security audit.

## Document set

- **27033-1:2015** — Overview and concepts.
- **27033-2:2022** — Guidelines for the design and implementation of network security.
- **27033-3:2022** — Reference networking scenarios (SOHO, enterprise, cloud, OT, IoT).
- **27033-4:2014** — Securing communications between networks using security gateways.
- **27033-5:2024** — Securing communications across networks using virtual private networks.
- **27033-6:2016** — Securing wireless IP network access.
- **27033-7:2024** — Guidelines for network virtualization.

References: `https://www.iso.org/standard/63461.html` (Part 2).

## Part-by-part binding

### Part 2 — Design and implementation

Network security design must address:

- **Network architecture**: segmentation, zones, conduits (per IEC 62443).
- **Network security controls**: firewall, IDS/IPS, DPI, DPI-SSL/TLS, NAC.
- **Network monitoring**: SNMP, sFlow, NetFlow, IPFIX, telemetry streaming (gNMI).
- **Network device hardening**: disable unused services, OS hardening.
- **Network change management**: PR-based change control, staging validation.
- **Network resilience**: redundancy, BGP multi-path, ECMP.

### Part 3 — Reference scenarios

| Scenario | Description | Required controls |
|---|---|---|
| SOHO | small office / home office | firewall, anti-malware, secure router |
| Enterprise | corporate network | segmentation, NAC, IDS/IPS, secure gateways |
| Cloud | IaaS / PaaS / SaaS | provider's controls + customer's controls (per ISO/IEC 27017) |
| OT | industrial network | per IEC 62443 (zones, conduits, SL-T) |
| IoT | constrained devices | per ETSI EN 303 645, ISO/IEC 30141 |

### Part 4 — Security gateways

Security gateways (firewalls, IDS/IPS, WAF, secure mail gateways) must be:

- Configured per default-deny policy.
- Audited per access log review.
- Updated per vendor's security update policy.
- Tested per penetration testing schedule.

### Part 5 — Virtual private networks (VPNs)

VPNs are governed by Part 5:

- IPsec: IKEv2 (RFC 7296), ESP, AES-256-GCM or ChaCha20-Poly1305.
- WireGuard: Curve25519, ChaCha20-Poly1305.
- OpenVPN: TLS 1.3, AES-256-GCM.
- AlwaysOn: split tunnel forbidden for sensitive workloads.
- AlwaysOn: full tunnel required.

### Part 6 — Wireless networks

- WPA3-Enterprise mandatory for enterprise Wi-Fi.
- WPA3-Personal mandatory for SOHO Wi-Fi.
- 802.11w (Management Frame Protection) mandatory.
- 802.11r (Fast BSS Transition) optional.
- 802.11k (Neighbor Reports) optional.

### Part 7 — Network virtualization

- Virtual network isolation: VLAN, VRF, VxLAN, Geneve.
- SDN security: encrypted control plane (TLS 1.3), authenticated API.
- Container network: Cilium CNI with eBPF, Calico, Weave.
- Network policy: default-deny, least privilege.

## Mandatory pre-flight (before adopting a new network component)

1. Network architecture is documented (zones, conduits).
2. Network security controls are documented (firewall, IDS/IPS, NAC).
3. Network monitoring is wired.
4. Network device hardening is documented.
5. Network change management is in place.
6. Network resilience is documented.

## Cross-reference

| Domain | Card |
|---|---|
| Routing | `BGP_RFC_4271_VERSION_GOVERNANCE.md`, `RPKI_RFC_8210_VERSION_GOVERNANCE.md`, `BGPSEC_RFC_8209_VERSION_GOVERNANCE.md`, `MANRS_GOVERNANCE.md` |
| VPN | `IPSEC_IKEV2_RFC_7296_VERSION_GOVERNANCE.md` |
| Wireless | (WPA3) Part 6 binding |
| OT | `IEC_62443_2024_IACS_GOVERNANCE.md`, `OT_SEGMENTATION_PLAYBOOK.md` |
| IoT | `ISO_IEC_30141_2018_IOT_GOVERNANCE.md`, `ETSI_EN_303_645_CYBER_GOVERNANCE.md` |

## Self-attestation cycle

Every 180 days:

1. Walk every network reference card.
2. Confirm conformance to the 27033 parts.
3. Confirm network architecture is current.
4. Update the next-review date.

## Sources

- ISO/IEC 27033-1:2015: `https://www.iso.org/standard/63461.html`
- ISO/IEC 27033-2:2022: `https://www.iso.org/standard/63461.html`
- ISO/IEC 27033-3:2022: `https://www.iso.org/standard/69045.html`
- ISO/IEC 27033-5:2024 (VPNs): `https://www.iso.org/standard/82070.html`
- ISO/IEC 27033-7:2024 (Network Virtualization): `https://www.iso.org/standard/82071.html`
