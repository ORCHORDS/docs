---
title: "Security Policy"
owner: "Security Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Security Policy

## Purpose

Define ORCHORDS security expectations without exposing system-specific
implementation details.

## Security principles

- **Govern:** security risk is owned and integrated with business decisions.
- **Identify:** assets, dependencies, data, suppliers, and material risks are
  understood at an appropriate level.
- **Protect:** access is least-privilege, secrets are protected, and secure
  defaults are preferred.
- **Detect:** security-relevant events and control failures are observable.
- **Respond:** incidents use defined command, communication, evidence, and
  containment processes.
- **Recover:** restoration is prioritized, validated, and followed by learning.

These principles align with NIST Cybersecurity Framework 2.0.

## Secure development

Software changes use reviewable source control, testing appropriate to risk,
secret detection, dependency management, least-privilege automation,
supply-chain integrity controls, and application-security verification where
appropriate.

See [Engineering Standards](../engineering/ENGINEERING_STANDARDS.md),
[Secure Design](../engineering/SECURE_DESIGN_THREAT_MODELING.md), and
[Software Supply Chain](../engineering/SOFTWARE_SUPPLY_CHAIN.md).

## Access and secrets

Access is granted to named identities, privilege is minimized, strong
authentication is required for privileged access where supported, and access is
revoked promptly when no longer needed. Secrets do not belong in public
documentation or source content.

## Vulnerability management

Vulnerabilities are prioritized by exploitability, exposure, business impact,
data impact, and available mitigations—not CVSS alone. Management targets are
defined in [Vulnerability Management SOP](../sop/VULNERABILITY_MANAGEMENT_SOP.md).

## Incident response

Security incidents follow
[Incident Management SOP](../sop/INCIDENT_MANAGEMENT_SOP.md) and
[Post-Incident Review SOP](../sop/POST_INCIDENT_REVIEW_SOP.md).

## Disclosure

External vulnerability reporting follows the
[Vulnerability Disclosure Policy](./VULNERABILITY_DISCLOSURE_POLICY.md).

## Assurance

Policies describe expectations. Evidence demonstrates implementation. Public
claims of certification, formal compliance, testing, or control implementation
require current evidence and approval.

## References

See [Standards](../standards/REFERENCES.md).
