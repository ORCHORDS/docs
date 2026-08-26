# soc2-compliance

**Issue:** SOC 2 Type 2 — security + availability audit
**Date:** 2026-08-09
**Status:** documented

## Symptom
An enterprise prospect asks "are you SOC 2?" You
say "no." They say "we'll evaluate you when you
are." You wish you'd started sooner.

## Root cause
**SOC 2 is the B2B SaaS baseline.** Implement it.

**Source:** AICPA SOC 2.

## The "SOC 2" concept

SOC 2 is an audit of trust services criteria:
- **Security:** Mandatory (Common Criteria)
- **Availability:** Optional
- **Confidentiality:** Optional
- **Processing Integrity:** Optional
- **Privacy:** Optional

For B2B SaaS, **Security + Availability + Confidentiality**
is typical.

## The "Type 1 vs Type 2" pattern

For Type 1 vs Type 2:
- **Type 1:** Point-in-time (3-4 months)
- **Type 2:** Operating over 3-12 months

For most, **Type 2** is the goal.

## The "13 phases" pattern

For 13 phases (90 days to audit-ready):
1. **Governance + policies** (Days 1-20)
2. **Access management** (Days 15-30)
3. **Change management** (Days 20-40)
4. **Monitoring + logging** (Days 25-50)
5. **Vulnerability management** (Days 30-55)
6. **Encryption + data** (Days 35-55)
7. **Incident response** (Days 40-65)
8. **Vendor management** (Days 45-65)
9. **HR + personnel** (Days 15-75)
10. **Business continuity** (Days 50-80)
11. **Availability** (Days 60-85)
12. **Confidentiality** (Days 65-85)
13. **Final readiness** (Days 80-90)

The phases are sequential.

## The "policies" pattern

For 11+ policies:
- **Information Security Policy** (master)
- **Acceptable Use Policy**
- **Access Control Policy**
- **Change Management Policy**
- **Risk Assessment Policy**
- **Incident Response Policy + playbook**
- **Vendor Management Policy**
- **Data Classification Policy**
- **Data Retention and Disposal Policy**
- **Business Continuity / DR Policy**
- **Backup Policy**
- **Encryption Policy**
- **Password Policy** (MFA)
- **Remote Work Policy**
- **Physical Security Policy**
- **Personnel Security Policy**
- **Secure Software Development Policy (SDLC)**
- **Vulnerability Management Policy**
- **Logging and Monitoring Policy**
- **Code of Conduct**

All policies: CEO-signed, annual review, accessible.

## The "Common Criteria" pattern

For CC1-CC9 (64 controls):
- **CC1:** Control environment
- **CC2:** Communication and info
- **CC3:** Risk assessment
- **CC4:** Monitoring activities
- **CC5:** Control activities
- **CC6:** Logical and physical access
- **CC7:** System operations
- **CC8:** Change management
- **CC9:** Risk mitigation

The 64 controls are the minimum.

## The "evidence" pattern

For evidence:
- **Access reviews:** Quarterly screenshots
- **Change tickets:** With approvals
- **Incident records:** Post-mortems
- **Vuln scan reports:** With remediation dates
- **Training completion:** Per employee
- **Vendor risk:** Questionnaires
- **Encryption config:** KMS screenshots
- **Backup restore:** Test results

Evidence is required.

## The "MFA" pattern

For MFA:
- **Production systems:** Required
- **Email:** Required
- **SSO provider:** Required
- **Cloud consoles:** Required

The MFA is enforced.

## The "access reviews" pattern

For access reviews:
- **Quarterly:** Every user, every system
- **Manager sign-off:** Required
- **Termination:** 24h (4h for privileged)

The reviews are quarterly.

## The "change management" pattern

For change:
- **Code review:** Required (branch protection)
- **CI/CD:** Automated tests
- **Production deploy:** Logged with deployer
- **Rollback:** Documented + tested
- **Emergency:** With retro

The changes are tracked.

## The "logging" pattern

For logging:
- **Centralized:** Datadog, Splunk, ELK
- **Security events:** Auth, authz, admin, data access
- **Retention:** 1+ year (sector may require 3+)
- **Tamper-proof:** Append-only
- **Alerts:** Suspicious patterns
- **SIEM:** For correlation

The logs are central.

## The "vulnerability management" pattern

For vuln:
- **Scanner:** Tenable, Qualys, Rapid7
- **Container scan:** In CI/CD
- **SAST:** Semgrep, Snyk, SonarQube
- **DAST:** API scanning
- **Patch SLAs:** Critical 7d, High 30d, Medium 90d
- **Pen test:** Annual

The vulns are tracked.

## The "encryption" pattern

For encryption:
- **At rest:** AES-256
- **In transit:** TLS 1.2+ (1.3 preferred)
- **Backups:** Encrypted
- **Key management:** AWS KMS, Vault
- **Key rotation:** Annual

The encryption is at rest + in transit.

## The "incident response" pattern

For IR:
- **Plan written**
- **Tabletop:** Annual
- **On-call rotation:** Defined
- **Runbooks:** Per scenario
- **Post-mortem template:** Per P1/P2
- **Customer comms template**

The IR is ready.

## The "vendor management" pattern

For vendors:
- **Inventory:** With criticality
- **SOC 2 / ISO 27001:** Collected for critical
- **DPAs:** Per GDPR
- **Risk assessment:** Annual
- **Sub-processor list:** Public

The vendors are managed.

## The "HR" pattern

For HR:
- **Background checks:** Where allowed
- **Security training:** On hire + annual
- **Phishing sim:** Quarterly
- **AUP signed:** By every employee
- **Offboarding:** Checklist

The HR is documented.

## The "BCP / DR" pattern

For BCP/DR:
- **Plan written**
- **RTO/RPO:** Per system
- **Backup testing:** Quarterly (actual restore)
- **DR test:** Annual
- **Redundancy:** Multi-AZ

The BCP/DR is tested.

## The "SOC 2 cost" pattern

For cost:
- **Type 1 + Type 2 (SMB):** $25k - $80k first year
- **Annual recurring:** $7k - $100k
- **Tooling:** Varies
- **Total first year:** $25k - $80k

The cost is significant.

## The "SOC 2 vs ISO 27001" choice

| Use case | Use |
|---|---|
| **US enterprise sales** | SOC 2 |
| **Global enterprise** | ISO 27001 + SOC 2 |
| **Federal** | FedRAMP |

For most apps, **SOC 2** is the baseline.

## The "SOC 2 anti-pattern" anti-patterns

### 1. Paperwork only
- **Issue:** No real security
- **Fix:** Real controls

### 2. No evidence
- **Issue:** Audit fails
- **Fix:** Collect evidence continuously

### 3. Skip tabletop
- **Issue:** No IR test
- **Fix:** Tabletop annually

### 4. No MFA
- **Issue:** Critical gap
- **Fix:** MFA everywhere

### 5. Skipping access reviews
- **Issue:** Stale access
- **Fix:** Quarterly reviews

## Verification
- **Test:** Controls are in place
- **Test:** Evidence is collected
- **Test:** IR plan is tested
- **Live:** Monitored
- **Audit:** Annual surveillance

## Gotchas
- **The "paperwork only" anti-pattern.** Real controls.
- **The "no evidence" anti-pattern.** Collect evidence.
- **The "no MFA" anti-pattern.** MFA everywhere.

## Related
- `compliance/iso-27001-compliance.md`
- `compliance/fedramp-compliance.md`
- `compliance/hipaa-compliance.md`
- `feature-cookbook-incident-response.md`
- AICPA: https://www.aicpa.org/topic/audit-assurance/audit-and-assurance-greater-than-soc-2
- Matproof: https://matproof.com/blog/soc-2-compliance-checklist-2026
- ComplyJet: https://www.complyjet.com/blog/soc-2-controls
