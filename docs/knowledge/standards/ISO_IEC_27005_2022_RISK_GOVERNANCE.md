---
title: ISO/IEC 27005:2022 Information Security Risk Management Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: ISO/IEC 27005:2022 (fourth edition, 2022-10) — "Information security, cybersecurity and privacy protection — Guidance on managing information security risks"; https://www.iso.org/standard/80585.html
---

# ISO/IEC 27005:2022 Information Security Risk Management Governance

## Scope

This card governs how `orchords-docs` evaluates information security risk management against ISO/IEC 27005:2022. It is the reference input for every reference card that touches risk, threat modeling, or control selection.

## Why this card exists

ISO/IEC 27005 is the dedicated risk-management standard for information security. It supersedes the risk-management guidance that was previously embedded in ISO/IEC 27001:2013 (now separated). Without an explicit card, the KB cites risk-management practices that do not survive an ISO/IEC 27005-aligned audit.

## Risk management process

ISO/IEC 27005:2022 defines a six-step process:

1. **Context establishment** — define scope, criteria, and stakeholders.
2. **Risk identification** — identify assets, threats, vulnerabilities, and consequences.
3. **Risk analysis** — assess the likelihood and impact of each risk.
4. **Risk evaluation** — compare analyzed risks against acceptance criteria.
5. **Risk treatment** — select and implement controls to modify risk.
6. **Risk acceptance** — formally accept residual risk.
7. **Communication and consultation** — throughout.
8. **Monitoring and review** — throughout.

References: `https://www.iso.org/standard/80585.html`.

## Asset model

The project enumerates the following asset classes:

| Asset class | Examples |
|---|---|
| Information | KB content, design docs, audit logs, telemetry |
| Software | reference implementations, scripts, configs |
| Physical | server hardware, network devices |
| Services | DNS, NTP, identity provider, monitoring |
| People | contributors, owners |
| Intangibles | reputation, customer trust |

## Threat catalog

The project maintains a threat catalog aligned with ENISA, MITRE ATT&CK, and OWASP:

- Adversarial threats: nation-state, organized crime, hacktivist, insider.
- Environmental threats: natural disaster, supply chain, pandemic.
- Accidental threats: human error, configuration drift.
- Structural threats: design flaw, missing control, deprecated dependency.

## Vulnerability catalog

The project maintains a vulnerability catalog aligned with CWE, CVE, and OWASP Top 10:

- CWE-79 (XSS), CWE-89 (SQLi), CWE-200 (Information Disclosure), CWE-269 (Improper Privilege Management), etc.

## Likelihood / impact scales

The project uses a 5x5 likelihood-impact matrix:

| Likelihood | Definition |
|---|---|
| 1 — Rare | unlikely to occur in the next 12 months |
| 2 — Unlikely | could occur but not expected |
| 3 — Possible | might occur in the next 12 months |
| 4 — Likely | will probably occur |
| 5 — Almost certain | expected to occur |

| Impact | Definition |
|---|---|
| 1 — Negligible | no observable effect |
| 2 — Minor | limited effect, recoverable |
| 3 — Moderate | significant effect, recoverable with effort |
| 4 — Major | severe effect, recovery requires significant resources |
| 5 — Catastrophic | unrecoverable, regulatory action, public trust loss |

## Risk acceptance criteria

| Risk score | Action |
|---|---|
| 1 — 4 | Accept, monitor |
| 5 — 9 | Treat (apply controls) |
| 10 — 15 | Treat, escalate to management |
| 16 — 25 | Avoid or transfer (insurance) |

## Control selection

The project uses ISO/IEC 27002 Annex A controls and the cross-walked controls from ISO/IEC 27017, ISO/IEC 27018, ISO/IEC 27701, NIST SP 800-53, and PCI-DSS.

## Mandatory pre-flight (before adopting a new risk-management decision)

1. Context is established.
2. Risks are identified, analyzed, evaluated.
3. Treatment plan is documented.
4. Residual risk is documented.
5. Acceptance is signed by the appropriate level of management.

## Cross-reference

| Domain | Card |
|---|---|
| Risk assessment | `NIST_SP_800_30_R1_RISK_ASSESSMENT_GOVERNANCE.md` |
| Threat modeling | (per attack-pattern catalog in this card) |
| AI risk | `ISO_IEC_27402_2024_AI_SECURITY_GOVERNANCE.md` |
| Privacy risk | `ISO_IEC_27701_2019_PIMS_GOVERNANCE.md` |
| OT risk | `IEC_62443_2024_IACS_GOVERNANCE.md` |
| Vendor risk | `ISO_IEC_27036_2` (not yet carded) |

## Self-attestation cycle

Every 180 days:

1. Walk the risk register.
2. Confirm context is current.
3. Confirm treatment plans are executed.
4. Update the next-review date.

## Sources

- ISO/IEC 27005:2022: `https://www.iso.org/standard/80585.html`
- ISO/IEC 27001:2022: `https://www.iso.org/standard/27001`
- ISO/IEC 27002:2022: `https://www.iso.org/standard/75652.html`
- NIST SP 800-30 Rev. 1: `https://csrc.nist.gov/publications/detail/sp/800-30/rev-1/final`
- ENISA Threat Landscape: `https://www.enisa.europa.eu/topics/cyber-threats/threats-and-trends`
- MITRE ATT&CK: `https://attack.mitre.org/`
