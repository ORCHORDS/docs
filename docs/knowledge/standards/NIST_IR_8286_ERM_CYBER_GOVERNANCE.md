# NIST IR 8286 Integrating Cybersecurity & Enterprise Risk Management Governance

## 1. Scope

This card governs ORCHORDS adoption of NIST IR 8286 ("Integrating Cybersecurity and Enterprise Risk Management") as the bridge between operational cyber-risk registers and the enterprise risk register reported to the board. It supplements ISO/IEC 27005 and ISO 31000.

## 2. Normative references

- NIST IR 8286 (2020), NIST IR 8286A (2021), NIST IR 8286B (2022), NIST IR 8286C (2023), NIST IR 8286D (2024).
- NIST CSF 2.0 (Govern function).
- ISO/IEC 27001:2022, ISO 31000:2018.
- ORCHORDS Enterprise Risk Charter (internal).

## 3. Risk register hierarchy

1. **Enterprise Risk Register**: board-level, owned by the Chief Risk Officer (CRO).
2. **Cyber Risk Register**: tier-1 subset, owned by the CISO.
3. **Operational Risk Registers**: per BU/Platform team, owned by the BU risk lead.
4. **Treatment records**: per risk, owned by the risk owner.

## 4. Risk taxonomy

| Tier | Description | Example |
| --- | --- | --- |
| Tier 1 (Enterprise) | Cross-org, board-tracked | Major supply-chain compromise |
| Tier 2 (Cyber) | Org-wide cyber, CISO-tracked | Customer data exfiltration |
| Tier 3 (Operational) | BU/team-scoped | Production outage in a non-critical service |
| Tier 4 (Acceptance) | Within BU tolerance | Vendor SLA slip with no business impact |

## 5. Risk elements (per IR 8286C schema)

- **Identifier**: RA-YYYY-NNNN.
- **Title and description**: business language; no internal jargon.
- **Threat and vulnerability**: linked to a CVE, threat actor, or scenario.
- **Likelihood (L)**: scale 1 (rare) to 5 (almost certain).
- **Impact (I)**: scale 1 (negligible) to 5 (severe).
- **Inherent risk**: L × I.
- **Controls**: mapped to NIST CSF subcategories.
- **Residual risk**: post-control L × I.
- **Risk response**: accept, mitigate, transfer, avoid.
- **Owner and review date**.

## 6. Reporting cadence

- Weekly: CISO → CRO cyber-risk summary.
- Monthly: CRO → Risk Committee register.
- Quarterly: CRO → Board Risk Report.
- Out-of-cycle: any Tier 1 risk with inherent risk ≥ 15.

## 7. Cyber-to-enterprise escalation triggers

- Any incident classified as SEV-1 or SEV-2 (per `INCIDENT_CLASSIFICATION.md`).
- Any data breach involving > 500 customer records.
- Any regulatory fine or notification.
- Any supply-chain compromise of a Critical dependency.

## 8. Tooling

- GRC platform: ServiceNow GRC for the enterprise register; Cyber Risk Manager (CRM) for the cyber register.
- Risk scoring: formula `L × I` computed in CRM, exported to GRC nightly.

## 9. Review cadence

This card is reviewed every 180 days. The next scheduled review is 2027-03-06. Updates to NIST IR 8286 series or the ORCHORDS Risk Charter trigger out-of-cycle updates.
