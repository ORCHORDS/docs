---
title: "ISO/IEC 27033-1:2015 Network Security — Overview and Concepts Version Transition Governance"
standard: "ISO/IEC 27033-1:2015"
publisher: "International Organization for Standardization (ISO) and International Electrotechnical Commission (IEC)"
category: "standards"
subcategory: "network-security"
canonical_url: "https://www.iso.org/standard/63461.html"
status: "approved"
classification: "public"
audience: "Network security architects, infrastructure security, security engineering"
last-reviewed: "2026-09-04"
review-cycle: "180 days"
next-review: "2027-03-03"
---

# ISO/IEC 27033-1:2015 Network Security Overview Version Transition Governance

## Profile

ISO/IEC 27033-1 is the overview and concepts document of the ISO/IEC 27033 family, providing network security guidance applicable to organizations using networking technology. It identifies network security risks, defines a network security framework, and references the more detailed controls in ISO/IEC 27033-2 through ISO/IEC 27033-7. The series replaces and broadens ISO/IEC 17945 (later withdrawn) and aligns with ISO/IEC 27001 Annex A controls.

The series is intended for architects, designers, implementers, and operators of networks who need a structured approach to network security.

## Identifier

| Field | Value |
| --- | --- |
| Standard | ISO/IEC 27033-1:2015 |
| Title | Information technology — Security techniques — Network security — Part 1: Overview and concepts |
| Family | ISO/IEC 27033 (6-part series) |
| Cross-reference | NIST SP 800-12; NIST SP 800-44; IETF RFC 4949 (Internet Security Glossary); ISO/IEC 27001 Annex A controls |

## Network Security Framework Components

| Component | Intent |
| --- | --- |
| Identify network security risks | Map network-related risks to organizational assets and operations. |
| Design network security controls | Apply secure-by-design principles; define protective controls. |
| Implement network security controls | Build, configure, and deploy network protection. |
| Operate network security controls | Monitor, manage, and maintain network protections. |
| Monitor and review | Audit, test, and improve network security posture. |

## ORCHORDS Profile

| Field | ORCHORDS convention |
| --- | --- |
| Adoption | Cite the overview for network security governance and as the navigation entry to the part-specific guides. |
| Asset mapping | Maintain a network asset inventory (Layer 2 through Layer 7) and dependencies. |
| Risk register | Tag risks with network components and reference the corresponding 27033 part. |
| Control implementation | Use 27033-2 (architecture) for network security architecture; 27033-4 (wireless) for Wi-Fi/5G; 27033-6 (security across networks) for inter-network connections. |
| Integration with ISMS | Map network security controls into ISO/IEC 27001 ISMS Annex A where applicable. |
| Audit | Audit network security controls at planned intervals against the framework and supporting parts. |

## Implementation Notes

- The 27033 series is intentionally modular; use Part 1 for the conceptual model and select the relevant part-specific guides for in-scope technologies.
- Pair with NIST SP 800-207 (zero trust architecture) for modern enterprise networks; 27033 and zero trust can co-exist when layered.
- Wireless (Part 4) is paired with IEEE 802.1X and Wi-Fi Alliance security specifications; document the chosen suite.
- IP multicast, VoIP, and SCADA networks require tailored guidance; consult the relevant 27033 part or sector overlay.

## Companion Documents

- [ISO/IEC 27001:2022 ISMS Version Guide](ISO_IEC_27001_2022_ISMS_VERSION_TRANSITION_GOVERNANCE.md)
- [NIST SP 800-12 Introduction to Information Security](NIST_SP_800_12_INFO_SEC_INTRODUCTION_GOVERNANCE.md)
- [NIST SP 800-207 Zero Trust Architecture](../reference/NIST_SP_800_207_ZERO_TRUST_GOVERNANCE.md)
- [Zero Trust Access Implementation Response](../playbooks/ZERO_TRUST_ACCESS_RESPONSE.md)
