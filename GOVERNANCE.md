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
4. **Reversible change.** Prefer changes with tested rollback or containment
   paths.
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
| Security risk acceptance | Security Lead | System/business owner |
| Production-impacting change policy | Operations Lead | Engineering Lead |
| Engineering quality policy | Engineering Lead | Security and Operations |
| Release approval policy | Release Manager | Engineering, Security, Operations |
| Public documentation approval | Documentation Maintainer | Content owner |
| Emergency exception | Incident Commander or accountable lead | Security/Operations as relevant |

## Policy hierarchy

When requirements conflict, apply the following order unless law or contract
requires otherwise:

1. Applicable law and contractual obligations
2. Security and safety requirements
3. Approved company policy
4. Approved SOPs
5. Team conventions and local guidance

A lower-level document cannot weaken a higher-level requirement without an
approved exception.

## Risk decisions

Risk decisions must record:

- the condition or uncertainty;
- business and technical impact;
- affected information or users;
- existing controls;
- treatment: avoid, reduce, transfer, or accept;
- accountable owner;
- expiry or review date;
- evidence supporting closure.

Use [Security Exception SOP](./sop/SECURITY_EXCEPTION_SOP.md) for deviations
from security controls.

## Metrics

Governance effectiveness is reviewed using trend data, not isolated numbers.
Useful indicators include overdue policy reviews, unresolved audit findings,
exception age, change failure rate, incident recurrence, recovery-test results,
and release rollback frequency.

## References

See [REFERENCES.md](./REFERENCES.md).
