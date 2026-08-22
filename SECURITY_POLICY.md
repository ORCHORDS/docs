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

This policy defines ORCHORDS security expectations without exposing
system-specific implementation details.

## Security principles

- **Govern:** security risk is owned, reviewed, and integrated with business
  decisions.
- **Identify:** assets, dependencies, data, and material risks are understood
  at an appropriate level.
- **Protect:** access is least-privilege, secrets are protected, and secure
  defaults are preferred.
- **Detect:** security-relevant events and control failures are observable.
- **Respond:** incidents use a defined command, communication, evidence, and
  containment process.
- **Recover:** restoration is prioritized, validated, and followed by learning.

These principles align with NIST Cybersecurity Framework 2.0.

## Secure development

Software changes MUST follow a reviewable source-control workflow. Depending on
risk, controls include:

- peer review and protected change paths;
- automated tests and security checks;
- dependency and vulnerability management;
- secret detection;
- least-privilege CI/CD permissions;
- immutable pinning or equivalent integrity controls for third-party
  automation;
- provenance and software bill of materials (SBOM) practices for release
  artifacts where justified by risk;
- security requirements and verification appropriate to the application.

See [Engineering Standards](./engineering/ENGINEERING_STANDARDS.md),
[Software Supply Chain](./engineering/SOFTWARE_SUPPLY_CHAIN.md), and
[REFERENCES.md](./REFERENCES.md).

## Access control

- Access is granted to named identities.
- Privilege is limited to the minimum required for current duties.
- Strong authentication is required for privileged access where supported.
- Shared credentials are prohibited unless a documented exception is
  necessary and compensating controls exist.
- Access is reviewed periodically and revoked promptly when no longer needed.

See [Access Management](./operations/ACCESS_MANAGEMENT.md).

## Secrets

Secrets must not be stored in public documentation or source content.
Repositories and CI systems should use approved secret-management mechanisms.
Suspected exposure triggers immediate containment, rotation/revocation where
applicable, evidence preservation, and incident assessment.

## Vulnerability management

Vulnerabilities are prioritized by exploitability, exposure, business impact,
data impact, and available mitigations—not CVSS alone.

Target response windows:

| Severity | Triage target | Remediation/mitigation target |
|---|---:|---:|
| Critical | 1 business day | As soon as safely practical; emergency process available |
| High | 3 business days | 14 calendar days |
| Medium | 10 business days | 60 calendar days |
| Low | 20 business days | Planned maintenance |

These are management targets, not guarantees. Risk acceptance requires an
approved, time-bounded exception.

## Incident response

Security incidents follow [Incident Management SOP](./sop/INCIDENT_MANAGEMENT_SOP.md).
The process is informed by NIST SP 800-61 Rev. 3 and CSF 2.0.

## Assurance and claims

This repository MUST NOT claim certification, formal compliance, penetration
testing, bug-bounty coverage, control implementation, or audit success without
current evidence and approval.

Policies describe expectations. Evidence demonstrates implementation.

## Exceptions

Use [Security Exception SOP](./sop/SECURITY_EXCEPTION_SOP.md).

## References

See [REFERENCES.md](./REFERENCES.md).
