---
title: "Governance"
owner: "Executive Leadership"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "180 days"
next-review: "2027-02-18"
---

# Governance

## Purpose

This policy defines how ORCHORDS assigns accountability, approves policy,
accepts risk, and resolves conflicts between speed, quality, security,
reliability, compliance, and customer impact.

## Governance principles

1. **Named accountability.** Every controlled document, material risk, major
   change, incident, and release has a responsible role.
2. **Evidence before assurance.** Public and internal claims must be supported
   by verifiable evidence.
3. **Least privilege and separation of duties.** Sensitive actions should not
   depend on one person's unchecked authority where practical.
4. **Reversible change.** Prefer changes with tested rollback or containment paths.
5. **Risk-based depth.** Controls become stronger as impact, exposure, or
   uncertainty increases.
6. **No silent exceptions.** Deviations from policy are time-bounded, owned,
   documented, and reviewed.
7. **Continuous improvement.** Incidents, near misses, review findings, and
   operational friction feed back into procedures and controls.

## Decision rights

| Decision | Accountable role | Required consultation |
|---|---|---|
| Company policy approval | Executive Leadership | Relevant functional lead |
| Enterprise risk acceptance | Accountable executive | Risk and functional owner |
| Security risk acceptance | Security Lead | System/business owner |
| Production-impacting change policy | Operations Lead | Engineering Lead |
| Engineering quality policy | Engineering Lead | Security and Operations |
| Release approval policy | Release Manager | Engineering, Security, Operations |
| Public documentation approval | Documentation Maintainer | Content owner |
| Emergency exception | Incident Commander or accountable lead | Relevant control owner |

## Policy hierarchy

When requirements conflict, apply the following order unless law or contract
requires otherwise:

1. Applicable law and contractual obligations
2. Security, privacy and safety requirements
3. Approved company policy
4. Approved SOPs
5. Team conventions and local guidance

A lower-level document cannot weaken a higher-level requirement without an
approved exception.

## Risk governance

Material risks use the
[Risk Management Policy](./RISK_MANAGEMENT_POLICY.md) and
[Risk Assessment SOP](../sop/RISK_ASSESSMENT_SOP.md).

## Metrics and assurance

Governance effectiveness is reviewed using trend data, not isolated numbers.
See [Control Assurance and Metrics](./CONTROL_ASSURANCE_METRICS.md).

## References

See the [Standards and Guidance Register](../standards/REFERENCES.md).
