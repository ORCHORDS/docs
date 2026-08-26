# soc2-cc6-logical-access-controls

**Issue:** Implementing SOC 2 CC6 logical and physical access control requirements
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
CC6 is the largest SOC 2 common criteria category. It covers logical access to systems, infrastructure, and data including authentication, authorization, and access provisioning/deprovisioning.

## Pattern / Solution
CC6.1 — Access restriction:
- Role-based access control (RBAC) documented and enforced
- Principle of least privilege for all roles
- Multi-factor authentication (MFA) required for all production systems
- Privileged access management (PAM) tool for admin credentials
- No shared credentials; individual accounts only

CC6.2 — Prior to system access:
- Formal access request and approval workflow (Jira/ServiceNow ticket required)
- Background checks completed before access granted
- Access control register maintained

CC6.3 — Deprovisioning:
- Terminate access within 24 hours of HR termination notification
- Quarterly access reviews (user certification) — remove unnecessary access
- Evidence: screenshots of access review approvals, termination tickets, access logs

CC6.6 — Threats from external sources:
- Web application firewall (WAF) in front of all public endpoints
- Intrusion detection system (IDS/IPS) logs reviewed daily
- Penetration test annually; critical findings remediated within 30 days

Evidence to collect per audit:
- User access lists by system (quarterly)
- Access review completion sign-offs
- MFA enrollment reports
- Terminated user deprovisioning tickets with timestamps

## Gotchas
- Auditors look for orphaned accounts from acquisitions or role changes
- Emergency/break-glass access must be logged and reviewed post-use
- Contractors and vendors need the same access controls as employees
- Access reviews must show approver names and dates — automated exports insufficient without sign-off

## Related
- `soc2-compliance.md`
- `soc2-cc7-system-operations.md`
