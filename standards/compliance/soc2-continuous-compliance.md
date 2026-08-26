# soc2-continuous-compliance

**Issue:** Maintaining SOC 2 compliance year-round rather than scrambling before audits
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
SOC 2 Type II auditors sample evidence across the entire audit period (typically 12 months). Point-in-time preparation fails because gaps anywhere in the period can result in findings.

## Pattern / Solution
Continuous compliance calendar:

Monthly:
- Vulnerability scan and remediation review
- Access review for privileged accounts
- Review alerts and incidents log
- Security awareness training completion rate check

Quarterly:
- Full user access review (all systems in scope)
- Vendor/third-party security review
- Business continuity plan review
- Security policy acknowledgment check

Annually:
- Penetration test
- Full risk assessment
- Policy reviews and updates
- Disaster recovery exercise
- Background check renewal for privileged users

Continuous (automated):
- MFA enrollment monitoring
- Configuration drift detection (AWS Config, Terraform Sentinel)
- Log retention verification
- Certificate expiry monitoring (alert at 30 days)

Assign control owners in a RACI matrix. Each owner responsible for their evidence cadence. Compliance platform sends reminders and tracks completion.

Build compliance into engineering workflow:
- PR template includes security checklist
- Deployment pipeline requires change ticket reference
- New vendor onboarding triggers security assessment workflow

## Gotchas
- One-month lapses in access reviews can result in exceptions even with good controls overall
- Evidence must cover the full audit period — pre-audit scramble cannot backfill 10 months
- Personnel changes (new CISO, new engineers) reset security training clocks
- Auditors look for consistency — intermittent monitoring is worse than no monitoring (implies lack of process)

## Related
- `soc2-evidence-collection-automation.md`
- `soc2-compliance.md`
