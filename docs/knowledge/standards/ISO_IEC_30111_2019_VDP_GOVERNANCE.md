---
title: ISO/IEC 29147:2018 / ISO/IEC 30111:2019 Vulnerability Disclosure and Handling Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: ISO/IEC 29147:2018 (vulnerability disclosure), ISO/IEC 30111:2019 (vulnerability handling), ISO/IEC 29147:2018/AMD 1:2024; https://www.iso.org/standard/72311.html, https://www.iso.org/standard/69725.html
---

# ISO/IEC 29147:2018 / ISO/IEC 30111:2019 Vulnerability Disclosure and Handling Governance

## Scope

This card governs how `orchords-docs` accepts, triages, coordinates, and discloses reports of vulnerabilities in any artifact the project publishes. It is binding for the GitHub repository (Security Advisories / Private Vulnerability Reporting), the GitHub Pages site, the release artifacts, and the reference implementations cited from KB cards.

## Why this card exists

ISO/IEC 29147 defines how to **receive** and **disclose** vulnerability information; ISO/IEC 30111 defines how to **handle** that information internally. A KB that publishes architecture cards without a documented vulnerability-disclosure path exposes end-users to reports with nowhere to land.

## Two-document split

- **ISO/IEC 29147:2018** — Vendor disclosure: receiving reports, providing information to reporters, publishing advisories, coordinating disclosure timing.
- **ISO/IEC 30111:2019** — Vendor handling: internal triage, reproduction, root-cause analysis, fix development, verification, advisory preparation.

The project documents both halves under a single card because every external reporter experiences both at once.

## Receiving reports (29147)

The project accepts vulnerability reports through:

| Channel | Use case | SLA |
|---|---|---|
| GitHub Security Advisories (private) | default reporter channel | acknowledge ≤ 3 business days |
| `security@orchords.com` | email-only reporters | acknowledge ≤ 5 business days |
| Encrypted PGP mail | high-severity / pre-disclosure | acknowledge ≤ 5 business days; PGP fingerprint published in `SECURITY.md` |

Public issue tracker reports of vulnerabilities are redirected to the private channel. The reporter is asked to confirm redaction of any public text that mentions the vulnerability.

## Triage workflow (30111)

```
[received] → [acknowledge] → [reproduce] → [score (CVSS 4.0)] → [triage severity]
   → [assign owner] → [fix development] → [verification] → [advisory draft]
   → [coordinated disclosure with reporter] → [public advisory release] → [post-mortem]
```

| Stage | Maximum time (CVSS 4.0 critical / high / medium / low) |
|---|---|
| Acknowledge | 1 / 3 / 5 / 10 business days |
| Reproduce | 5 / 10 / 20 / 30 business days |
| Triage severity | 1 / 2 / 5 / 10 business days |
| Fix development | 30 / 60 / 90 / 120 business days |
| Verification | 5 / 10 / 20 / 30 business days |
| Advisory draft | 5 / 10 / 15 / 20 business days |
| Coordinated disclosure window | 90 / 90 / 60 / 30 days |

The reporter may request a longer coordinated disclosure window; the project honors reasonable requests in writing.

## CVSS scoring

The project scores every vulnerability with **CVSS 4.0** as the primary vector, supplemented by CVSS 3.1 only when the reporter or downstream tooling requires it. CVSS 4.0 introduces supplemental metrics (Safety, Automatable, Recovery, Value Density, Vulnerability Response Effort, Provider Urgency) that the project uses to assign severity beyond CVSS 3.1's Base score.

Severity thresholds:

| CVSS 4.0 score | Severity | SLA |
|---|---|---|
| 9.0 — 10.0 | Critical | ≤ 30 day fix window |
| 7.0 — 8.9 | High | ≤ 60 day fix window |
| 4.0 — 6.9 | Medium | ≤ 90 day fix window |
| 0.1 — 3.9 | Low | ≤ 120 day fix window |

## Disclosure policy

- **Coordinated disclosure**: the project commits to a 90-day window for critical/high severity issues and 30-day for medium/low, in line with `disclose.io` Core Terms.
- **Public advisory channels**: GitHub Security Advisories (primary), project mailing list (secondary).
- **CVE assignment**: every accepted vulnerability gets a CVE via GitHub's CNA. The CVE record is published as soon as the fix is available or the coordinated disclosure window closes, whichever is earlier.

## Handling of declined reports

Reports that the project cannot reproduce or that fall outside scope receive a written reply within 5 business days, with:

1. A clear statement that the report is declined.
2. The technical reason (e.g., "the reported file path does not exist in the published release").
3. An invitation to provide additional context if the reporter believes the decline is in error.
4. A point of contact for escalation (the `ORCHORDS.COM` token owner).

## Safety-net rules

- Vulnerabilities under active exploitation are escalated to **emergency** (fix within 7 days, advisory release immediately, no coordinated-disclosure window).
- Reporter anonymity is preserved unless the reporter explicitly opts in to public credit.
- The project does not pursue legal action against good-faith security research conducted within the scope of this card.

## Mandatory pre-flight (before shipping a release that contains a security fix)

1. CVE is reserved via the GitHub CNA.
2. Security advisory text is drafted using the GHSA template.
3. The fix branch is reviewed by `ORCHORDS.COM` token.
4. A regression test is committed alongside the fix.
5. The release tag includes a `SECURITY:` line in the changelog.
6. `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md` is updated if severity is Critical or High.

## Self-attestation cycle

Every 180 days:

1. Walk the prior cycle's reported vulnerabilities and confirm every accepted report has a GHSA / CVE identifier.
2. Verify the published security advisory text does not leak unpatched exploit detail beyond what the fix prevents.
3. Update the next-review date.

## Sources

- ISO/IEC 29147:2018: `https://www.iso.org/standard/72311.html`
- ISO/IEC 30111:2019: `https://www.iso.org/standard/69725.html`
- ISO/IEC 29147:2018/AMD 1:2024 — vulnerability disclosure for ICT products: `https://www.iso.org/standard/87285.html`
- CVSS 4.0 specification: `https://www.first.org/cvss/v4.0/specification-document`
- GHSA workflow documentation: `https://docs.github.com/en/code-security/security-advisories`
- disclose.io Core Terms: `https://disclose.io/`
