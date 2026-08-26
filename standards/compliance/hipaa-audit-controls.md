# hipaa-audit-controls

**Issue:** Implementing HIPAA Security Rule audit control requirements (45 CFR 164.312(b))
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
HIPAA requires audit controls to record and examine activity on systems containing or using ePHI. OCR audits and breach investigations heavily scrutinize audit log adequacy and review procedures.

## Pattern / Solution
Required audit events (NIST guidance 800-66):
- User login and logout (success and failure)
- Access to ePHI records (view, create, modify, delete)
- System administrator activities
- Application errors related to ePHI
- Firewall and network access logs

Log retention: minimum 6 years (matches HIPAA record retention); recommend 7 years for breach investigation coverage.

Audit log implementation:
```
AWS CloudTrail: all API calls to S3 buckets and RDS containing ePHI
Application logging: log user_id, action, resource_id, timestamp, IP for all ePHI access
Database: enable audit logging for SELECT/INSERT/UPDATE/DELETE on ePHI tables
Centralize: ship all logs to SIEM (Splunk, Elasticsearch) with tamper-evident storage
```

Review procedures:
- Automated alerts for: failed login attempts (>3), off-hours access, bulk exports
- Weekly review of privileged user activity
- Monthly review of access patterns for anomalies
- Document reviews: log date, reviewer name, findings

Audit log protection:
- Logs must be write-once or tamper-evident (separate account, Object Lock)
- Access to logs restricted to Security/Compliance team
- Logs encrypted at rest

## Gotchas
- Logging without review is insufficient — OCR requires evidence of regular review
- Audit logs themselves are considered ePHI if they contain patient identifiers — protect accordingly
- Logs must be comprehensive enough to reconstruct all ePHI access after a breach
- 6-year retention applies to documentation; logs may need same retention period

## Related
- `hipaa-administrative-safeguards.md`
- `hipaa-phi-handling.md`
- `audit-log-mandatory.md`
