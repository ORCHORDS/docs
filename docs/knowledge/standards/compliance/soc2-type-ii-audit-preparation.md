# SOC 2 Type II Audit Preparation

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your sales team loses enterprise deals because prospects require SOC 2
certification. You have no formal documentation of security controls,
access reviews, or change management processes. When asked "how do you
protect customer data?", the answer is tribal knowledge spread across
engineering, not a documented and audited program. The gap between your
actual security posture and what you can prove to an auditor is large.

## Context

SOC 2 (Service Organization Control 2) is an auditing framework
developed by the AICPA that evaluates an organization's controls
relevant to the Trust Services Criteria: Security, Availability,
Processing Integrity, Confidentiality, and Privacy. Type I assesses
control design at a point in time; Type II assesses control operating
effectiveness over a period (typically 6-12 months). In 2026, AI-powered
compliance platforms (Vanta, Drata, Secureframe, Sprinto) automate
evidence collection and continuous monitoring, reducing the engineering
burden from weeks of manual evidence gathering to largely automated
workflows. Most SaaS companies target Security and Availability criteria
for their initial audit.

## Trust Services Criteria

| Criterion | What it covers | Common for SaaS? |
|---|---|---|
| **Security** (CC) | Protection against unauthorized access | Always included |
| **Availability** (A) | System uptime and performance | Usually included |
| **Processing Integrity** (PI) | Accurate, timely data processing | Sometimes (fintech, data) |
| **Confidentiality** (C) | Protection of confidential information | Sometimes |
| **Privacy** (P) | Personal information handling (AICPA criteria) | Rarely (use GDPR instead) |

## Engineering controls checklist

### Access management

| Control | Implementation | Evidence |
|---|---|---|
| SSO/MFA for all systems | Okta/Azure AD with MFA enforced | IdP configuration screenshot |
| Role-based access control | Defined roles with least privilege | Access matrix document |
| Quarterly access reviews | Review and revoke unnecessary access | Access review records |
| Offboarding within 24 hours | Automated deprovisioning on termination | HRIS → IdP automation logs |
| No shared credentials | Individual accounts for all systems | IAM policy, no shared keys |

### Change management

| Control | Implementation | Evidence |
|---|---|---|
| All changes via PR | Branch protection requiring PR review | GitHub branch protection settings |
| Code review required | Minimum 1 reviewer approval | PR merge history |
| CI/CD pipeline | Automated testing before deploy | CI configuration, test results |
| No direct production access | Deploy via pipeline, not SSH | IAM policies, bastion logs |
| Change log maintained | Git history + deploy logs | Automated from CI/CD |

### Infrastructure security

| Control | Implementation | Evidence |
|---|---|---|
| Encryption at rest | Database encryption, disk encryption | Cloud provider config |
| Encryption in transit | TLS 1.2+ for all connections | SSL certificate config |
| Network segmentation | VPC, security groups, private subnets | Network architecture diagram |
| Vulnerability scanning | Automated scanning (Snyk, Dependabot) | Scan results and remediation |
| Logging and monitoring | Centralized logging, alerting | Log aggregation config |

### Incident management

| Control | Implementation | Evidence |
|---|---|---|
| Incident response plan | Documented runbook with roles | IRP document |
| Incident tracking | Ticketing system for incidents | Incident tickets |
| Post-incident review | Blameless postmortems | Postmortem documents |
| Communication plan | Status page, stakeholder notification | Communication templates |

## Audit timeline

```
Month 1-2:  Gap assessment → Identify missing controls
Month 2-3:  Remediation → Implement missing controls
Month 3-4:  Documentation → Write policies and procedures
Month 4:    Readiness assessment → Internal audit or platform check
Month 5-10: Observation period → Controls operate for 6 months
Month 10-11: Audit fieldwork → Auditor examines evidence
Month 11-12: Report → SOC 2 Type II report issued
```

### Accelerated timeline (with compliance platform)

```
Month 1:   Platform setup → Connect systems, auto-collect evidence
Month 1-2: Gap analysis → Platform identifies missing controls
Month 2-3: Remediation → Fix gaps with platform guidance
Month 3:   Readiness → Platform confirms audit-readiness
Month 3-9: Observation period → Continuous monitoring
Month 9-10: Audit → Auditor reviews platform-collected evidence
Month 10:  Report → SOC 2 Type II report issued
```

## Compliance platform comparison

| Platform | Automation | Integrations | Starting price |
|---|---|---|---|
| **Vanta** | Continuous monitoring, auto-evidence | 300+ | ~$10k/year |
| **Drata** | Real-time control monitoring | 100+ | ~$10k/year |
| **Secureframe** | Automated evidence collection | 150+ | ~$8k/year |
| **Sprinto** | Risk-first automation | 100+ | ~$8k/year |

All platforms integrate with cloud providers (AWS, GCP, Azure), identity
providers (Okta, Google), code repositories (GitHub, GitLab), and
common SaaS tools.

## Anti-patterns

- **Treating SOC 2 as a one-time project** — SOC 2 Type II requires
  continuous control operation, not a one-time effort. Controls must
  work consistently throughout the observation period.
- **Compliance theater** — writing policies that describe ideal
  processes without actually implementing them. Auditors test whether
  controls actually operate, not just whether policies exist.
- **Engineering-only approach** — SOC 2 touches HR (background checks,
  security training), legal (vendor management, data processing), and
  management (risk assessment, board reporting). It is not just an
  engineering task.
- **Manual evidence collection** — spending engineering weeks pulling
  screenshots, logs, and configuration exports for the auditor. Use a
  compliance platform to automate evidence collection.

## Gotchas

- **Observation period is non-negotiable** — Type II requires 6-12
  months of control operation evidence. You cannot retroactively create
  this evidence. Plan the observation period before engaging an auditor.
- **Auditor selection matters** — SOC 2 audits are performed by licensed
  CPA firms. Costs range from $20k-$80k depending on scope and firm.
  Smaller firms (Johanson Group, Prescient Assurance) serve startups;
  Big Four firms serve enterprises.
- **Scope creep** — including all Trust Services Criteria in the first
  audit increases cost and complexity. Start with Security (required)
  and Availability (expected by most customers). Add criteria in
  subsequent years.
- **Shared responsibility model** — for cloud-hosted SaaS, your SOC 2
  report covers your controls, not the cloud provider's. Reference the
  cloud provider's own SOC 2 report (AWS, GCP, Azure all publish them)
  for infrastructure controls.

## Verification

- All five engineering control domains are implemented and documented.
- Compliance platform continuously monitors control effectiveness.
- Quarterly access reviews are conducted and documented.
- Incident response plan is tested at least annually.
- Observation period has begun with continuous evidence collection.
- Auditor is selected and engagement letter is signed.

## Related

- `documentation/docs/policies/compliance/gdpr-data-protection.md`
- `documentation/docs/policies/security/owasp-api-top-10-2023.md`
- `documentation/docs/policies/lessons/blameless-postmortem-incident-review.md`

## Source URLs (verified 2026-08-16)

- Secureframe SOC 2 checklist — https://secureframe.com/blog/soc-2-compliance-checklist
- SOC 2 audit timeline — https://www.konfirmity.com/blog/soc-2-audit-timeline
- SOC 2 Type II for engineering teams — https://www.stripesys.com/blog/soc2-type-ii-engineering-teams
- SOC 2 preparation guide — https://sprinto.com/blog/how-to-prepare-for-soc-2-audit/
