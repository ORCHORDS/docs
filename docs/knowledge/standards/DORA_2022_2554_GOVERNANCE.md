# Digital Operational Resilience Act (EU) 2022/2554 Governance

## 1. Scope

This card governs ORCHORDS adoption of Regulation (EU) 2022/2554 — the Digital Operational Resilience Act (DORA) — for financial entities and their critical ICT third-party service providers. It applies to all in-scope entities as defined by DORA Articles 2-4.

## 2. Normative references

- Regulation (EU) 2022/2554 (DORA), in force since 16 January 2023, applicable from 17 January 2025.
- Commission Delegated Regulation (EU) 2024/1772 (RTS on ICT risk management tools).
- Commission Delegated Regulation (EU) 2024/1774 (RTS on classification of ICT-related incidents).
- Commission Implementing Regulation (EU) 2024/2956 (ITS on registers of information).
- ISO/IEC 27001:2022, ISO/IEC 27002:2022, NIST SP 800-53 Rev. 5 — for control mapping.

## 3. Pillars and ORCHORDS obligations

1. **ICT risk management** — Article 5-16: identify, protect, detect, respond, recover.
2. **ICT incident reporting** — Article 17-23: classify and report significant ICT-related incidents within strict timelines.
3. **Digital operational resilience testing** — Article 24-27: annual testing, threat-led penetration testing (TLPT) every 3 years.
4. **ICT third-party risk** — Article 28-44: register of information, critical service-provider designation, exit strategies.
5. **Information sharing** — Article 45: voluntary threat intelligence sharing arrangements.

## 4. ICT risk management controls

| Control area | DORA reference | ORCHORDS implementation |
| --- | --- | --- |
| Governance | Art. 5-6 | Quarterly board report; CISO sign-off on residual risk |
| Identification | Art. 7-8 | Asset inventory, threat intelligence, dependency mapping |
| Protection | Art. 9 | Hardened baselines (CIS K8s v1.9, NIST 800-53), zero-trust network |
| Detection | Art. 10 | SIEM with UEBA, anomaly detection across ICT estate |
| Response & recovery | Art. 11-12 | BCP/DRP tested quarterly, RTO/RPO documented per critical service |
| Backup | Art. 12(3-5) | Immutable backups, restore drills quarterly, off-site cold storage |
| Learning | Art. 13 | Post-incident review, root-cause into risk register |

## 5. Incident classification

DORA aligns with the **four severity classes** defined by the RTS 2024/1774:

| Class | Definition | Initial notification | Intermediate | Final |
| --- | --- | --- | --- | --- |
| Major | Severe service disruption or impact on customers | ≤ 4 h from classification | ≤ 72 h | ≤ 1 month |
| Significant | Material impact on operations | ≤ 4 h | ≤ 72 h | ≤ 1 month |
| Notable | Limited operational impact | Weekly batch reporting | n/a | n/a |
| Informational | No immediate operational impact | Quarterly aggregated report | n/a | n/a |

## 6. Third-party risk register

- Maintain the **DORA register of information** per Article 28(3), in the format prescribed by ITS 2024/2956.
- For each critical ICT service provider, document: service description, function criticality, data processed, substitutability, exit-strategy timeline, and concentration risk.
- Submit register updates to the competent authority on request.

## 7. Testing cadence

- Annual vulnerability assessment and penetration test for all ICT systems.
- TLPT every 3 years based on the TIBER-EU framework; scope approved by the competent authority.
- Maintain test artefacts (scope, findings, remediation evidence) for at least 5 years.

## 8. Review cadence

This card is reviewed every 180 days. The next scheduled review is 2027-03-06. DORA regulatory technical standards and ESA joint statements trigger out-of-cycle updates.
