# soc2-type2-controls-mapping

**Issue:** Mapping SOC 2 Type II Trust Services Criteria to concrete engineering controls for audit evidence
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
SOC 2 Type II audits assess whether controls were operating effectively over a period (typically 6–12 months). Auditors require evidence — not just policies. Engineering teams frequently fail audits because controls exist in policy documents but are not implemented consistently in code and infrastructure. This entry maps the most commonly tested criteria to tangible artifacts.

## Pattern / Solution
**Security (CC6–CC9) — most heavily tested:**

| Criteria | Control | Evidence artifact |
|---|---|---|
| CC6.1 | Logical access restricted to authorised users | IAM policy exports, access review quarterly sign-off |
| CC6.2 | New access requires approval | Ticketing system records (e.g., Jira) |
| CC6.3 | Access removed within 24h of termination | HR offboarding checklist + IAM diff |
| CC6.6 | Encryption in transit (TLS 1.2+) | SSL Labs scan report, nginx/ALB config |
| CC6.7 | Encryption at rest | Cloud KMS key policy, DB encryption settings screenshot |
| CC7.1 | Vulnerability detection in place | Dependabot/Snyk scan history, CVSS scoring log |
| CC7.2 | Security incidents logged and managed | Incident tickets with timeline |
| CC8.1 | Change management process | Git PR history, deployment approvals |
| CC9.2 | Vendor risk assessed | Vendor assessment records |

**Availability (A1):**

```
A1.1 — Performance capacity monitored
  → CloudWatch/Datadog dashboards + alert configuration export

A1.2 — Environmental threats addressed
  → Business continuity plan, DR test results

A1.3 — Recovery objectives documented and tested
  → RTO/RPO targets + last DR drill date
```

**Confidentiality (C1):**
- Data classification policy with labeled data stores.
- Encryption key rotation logs.

**Processing Integrity (PI1):**
- Input validation test suite results.
- Error rate monitoring with alerting thresholds.

**Privacy (P1–P8):**
- Consent records, DSR completion log, privacy notice version history.

**Building evidence continuously:**
```yaml
# Example: automated evidence collection in CI
steps:
  - name: Export IAM policy snapshot
    run: aws iam get-account-authorization-details > evidence/iam-$(date +%F).json
  - name: Run dependency scan
    run: snyk test --json > evidence/snyk-$(date +%F).json
```

Store evidence in a dedicated, immutable S3 bucket or similar. Auditors expect to see a consistent trail across the audit period, not a snapshot prepared the week before the audit.

## Gotchas
- Type II requires evidence spanning the **entire** audit period — a control implemented one month before audit end covers only that month.
- Personnel changes must be reflected in access reviews; auditors cross-reference HR records against IAM.
- Automated controls are preferred over manual ones; manual controls require documented approvals for every instance.
- Subservice organisations (e.g., AWS) have their own SOC 2 report — request and review the complementary user entity controls (CUECs) they assign to you.
- "Management review" controls need documented reviewer sign-off, not just meeting minutes.

## Related
- `soc2-compliance.md`
- `audit-log-mandatory.md`
- `vendor-security-assessment.md`
- `security-incident-response-plan.md`
