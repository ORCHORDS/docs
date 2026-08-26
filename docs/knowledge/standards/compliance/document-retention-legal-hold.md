# document-retention-legal-hold

**Issue:** Document retention schedules, legal hold procedures, and eDiscovery readiness
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Organizations must retain records for legally required minimum periods and suspend normal deletion when litigation or investigation is reasonably anticipated (legal hold). Failure results in spoliation sanctions and adverse inference instructions.

## Pattern / Solution
Document retention schedule (common categories):

| Category | Retention Period | Legal Basis |
|----------|-----------------|-------------|
| Financial records | 7 years | IRS, most tax authorities |
| HR records (employment) | 7 years post-termination | EEOC, state law |
| Corporate records (board minutes, formation) | Permanent | Corporate law |
| Contracts | 7 years post-expiration | Statute of limitations |
| GDPR processing records (RoPA) | Duration of processing + 3 years | GDPR Art. 30 |
| HIPAA records | 6 years from creation or last effective date | HIPAA |
| PCI DSS audit logs | 12 months online; 12 months offline | PCI DSS Req 10.7 |
| Security incident records | 3-5 years | Internal; some regulations require 5 |
| Tax-related emails | 7 years | IRS guidance |

Legal hold procedure:
1. Trigger: litigation filed, investigation opened, or reasonably anticipated
2. Issue hold notice within 24 hours to all custodians (email + HR record)
3. Suspend automated deletion for all potentially relevant data (files, emails, Slack, databases)
4. Collect and preserve hold data to isolated repository
5. Document hold: issuer, date, scope, custodians, systems covered
6. Quarterly hold review: confirm still active, add new custodians as identified
7. Release hold: written release notice; resume normal deletion; document release date

eDiscovery readiness:
- Map data locations (email, Slack, Jira, databases, file shares)
- Ensure data can be searched and exported within reasonable timeframe
- Cloud data: understand provider retention and export capabilities

## Gotchas
- "Reasonably anticipated" starts the hold clock — waiting for a complaint to be filed is too late
- Over-retention creates its own risk — if you retain data beyond policy, it may be discoverable
- Slack and other collaboration tools have retention settings that must be overridden by legal hold
- Third-party data (lawyers' files, accountants' records) may also be subject to hold — notify them

## Related
- `gdpr-data-retention-policy.md`
- `audit-log-mandatory.md`
- `hipaa-audit-controls.md`
