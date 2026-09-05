---
title: NIST SP 800-161 Rev. 2 Cybersecurity Supply Chain Risk Management (C-SCRM) Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: NIST SP 800-161 Rev. 2 (May 2024) — Cybersecurity Supply Chain Risk Management Practices, Systems, and Components; NIST SP 800-161 Rev. 1 (February 2022 — SCRM); NIST IR 8276 (Key Practices); https://csrc.nist.gov/publications/detail/sp/800-161/rev-2/final
---

# NIST SP 800-161 Rev. 2 Cybersecurity Supply Chain Risk Management (C-SCRM) Governance

## Scope

This card governs how `orchords-docs` evaluates Cybersecurity Supply Chain Risk Management (C-SCRM) against NIST SP 800-161 Rev. 2. It is the reference input for any KB card that touches vendor risk, third-party assessment, or component security.

## Why this card exists

NIST SP 800-161 Rev. 2 (May 2024) supersedes Rev. 1 with expanded coverage of software supply chain, hardware supply chain, services supply chain, and ICT-supply chain. Without an explicit card, the KB cites vendor-risk practices that do not survive a federal-aligned audit.

## Document set

- **NIST SP 800-161 Rev. 2** (May 2024) — Cybersecurity Supply Chain Risk Management.
- **NIST SP 800-161 Rev. 1** (February 2022) — C-SCRM (legacy).
- **NIST IR 8276** — Key Practices in C-SCRM.
- **NIST SP 800-218 SSDF v1.1** — software-specific counterpart.

References: `https://csrc.nist.gov/publications/detail/sp/800-161/rev-2/final`.

## C-SCRM domains

NIST SP 800-161 Rev. 2 organizes C-SCRM into four domains:

| Domain | Description |
|---|---|
| 1 — Governance | policies, roles, risk management strategy |
| 2 — Risk Assessment | threat + vulnerability + impact for the supply chain |
| 3 — Controls | protective controls at every stage |
| 4 | Assurance | attestation, audit, monitoring |

## Enterprise-level practices

| Control Family | Description |
|---|---|
| GV.SC | Governance — supply chain risk management strategy |
| ID.SC | Identification — supplier / vendor / component inventory |
| PR.SC | Protection — supplier access, secure development |
| DE.SC | Detection — anomalous supplier behavior |
| RS.SC | Response — supplier incident response |
| RC.SC | Recovery — supplier continuity |

(Mapped to NIST CSF 2.0 SC categories.)

## Supplier-tier model

NIST SP 800-161 Rev. 2 introduces a supplier-tier model:

- **Tier 1** — direct supplier (first-party).
- **Tier 2** — supplier of Tier 1.
- **Tier 3+** — supplier of Tier 2, etc.

The project tracks at least Tier 1 and Tier 2 suppliers; Tier 3 is best-effort.

## Key practices

Per NIST IR 8276 / SP 800-161 Rev. 2:

1. **Establish a formal C-SCRM program**.
2. **Identify suppliers and components**.
3. **Assess supplier risk**.
4. **Define contractual controls** (SLAs, security obligations).
5. **Implement protective controls** at the supplier boundary.
6. **Monitor supplier security posture** continuously.
7. **Respond to supplier incidents** in coordination with the supplier.
8. **Recover** from supplier-driven disruptions.

## Component-level practices

For software components:

- Pin dependencies by commit SHA (per `TERRAFORM_VERSION_GOVERNANCE.md`).
- Sign SBOM and provenance (per `SLSA_VERSION_GOVERNANCE.md`).
- Validate signatures on adoption.
- Continuously monitor for CVEs.

For hardware components:

- Tamper-evident packaging.
- Hardware bill of materials (HBOM).
- Trusted supply chain attestation.

For services:

- SOC 2 Type II or ISO 27001 attestation.
- Penetration test report.
- Subprocessor register.

## Mandatory pre-flight (before adopting a new supplier)

1. The supplier is in the vendor inventory.
2. The supplier tier is documented.
3. The supplier risk assessment is documented.
4. The contractual controls are agreed.
5. The supplier attestation is on file.

## Cross-reference

| Domain | Card |
|---|---|
| Software | `SLSA_VERSION_GOVERNANCE.md` |
| SSDF | `NIST_SP_800_218_SSDF_GOVERNANCE.md` |
| Risk | `ISO_IEC_27005_2022_RISK_GOVERNANCE.md` |
| Vendor risk | (deferred) |

## Self-attestation cycle

Every 180 days:

1. Walk every KB reference card that touches a supplier.
2. Confirm supplier risk assessment is current.
3. Confirm attestation is on file.
4. Update the next-review date.

## Sources

- NIST SP 800-161 Rev. 2: `https://csrc.nist.gov/publications/detail/sp/800-161/rev-2/final`
- NIST SP 800-161 Rev. 1: `https://csrc.nist.gov/publications/detail/sp/800-161/rev-1/final`
- NIST IR 8276: `https://csrc.nist.gov/publications/detail/nistir/8276/final`
- NIST SSDF: `https://csrc.nist.gov/publications/detail/sp/800-218/final`
- CISA ICT Supply Chain: `https://www.cisa.gov/ict-supply-chain-toolkit`
