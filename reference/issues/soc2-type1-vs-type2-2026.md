# soc2-type1-vs-type2-2026

**Issue:** SOC 2 Type 1 vs Type 2 — audit selection
**Date:** 2026-08-09
**Status:** documented

## Symptom
Enterprise procurement asks for SOC 2. You do
Type 1. They say "we need Type 2." You realize
Type 1 isn't enough. 9-12 months later you have
Type 2. Meanwhile, deals slipped.

## Root cause
**Type 1 = design. Type 2 = operating.** Different.

**Source:** AICPA + TrustCloud 2026.

## The "SOC 2" concept

SOC 2:
- **Type 1:** Design at a point
- **Type 2:** Operating over 6-12 months
- **TSC:** Trust Services Criteria
- **Auditor:** CPA firm
- **Use:** SaaS procurement

The SOC 2 is the audit.

## The "Type 1" pattern

For Type 1:
- **When:** Point in time
- **Tests:** Design only
- **Window:** Single date
- **Use:** First-time filer
- **Ages out:** Fast

The Type 1 is design.

## The "Type 2" pattern

For Type 2:
- **When:** 6-12 months
- **Tests:** Design + operating
- **Window:** Historical
- **Use:** Enterprise
- **Ages out:** Annual renewal

The Type 2 is operating.

## The "observation window" pattern

For window:
- **Minimum:** 6 months (rare)
- **Norm:** 9-12 months
- **First:** Often Type 1 to bridge
- **Renewal:** Annual
- **Trend:** Stretching up

The window is per audit.

## The "5 TSCs" pattern

For criteria:
- **Security:** Mandatory
- **Availability:** Optional
- **Confidentiality:** Optional
- **Processing Integrity:** Optional
- **Privacy:** Optional
- **Scope:** Per commitment

The 5 are the TSC.

## The "CC1-CC9" pattern

For common:
- **CC1:** Control environment
- **CC2:** Communication
- **CC3:** Risk assessment
- **CC4:** Monitoring
- **CC5:** Control activities
- **CC6:** Logical + physical
- **CC7:** System ops
- **CC8:** Change management
- **CC9:** Risk mitigation

The 9 are the common.

## The "readiness assessment" pattern

For pre-audit:
- **Internal:** Dry-run
- **Identify:** Gaps
- **Fix:** Before window
- **Why:** Don't expose gaps
- **When:** Pre-window

The readiness is pre-audit.

## The "evidence-as-code" pattern

For evidence:
- **API:** Pull from systems
- **IdP:** SSO logs
- **HRIS:** Joiners/leavers
- **Cloud:** AWS/GCP audit
- **No screenshots:** Repeatable

The evidence is automated.

## The "subservice organization" pattern

For vendors:
- **AWS/Cloudflare/etc.:** In scope
- **Method:** Inclusive (CAR) or carve-out
- **Missing:** Frequent finding
- **Why:** Your control over vendor
- **Fix:** Document

The subservice is documented.

## The "scope decision" pattern

For scope:
- **Security:** Always
- **PII processing:** + Privacy
- **Uptime:** + Availability
- **Customer choice:** Per service
- **Why:** Cost + signal

The scope is per commitment.

## The "Type 1 only" anti-pattern

For Type 1 only:
- **Issue:** Enterprise rejects
- **Fix:** Plan Type 2

The plan is Type 2.

## The "screenshot evidence" anti-pattern

For screenshots:
- **Issue:** Not reproducible
- **Fix:** API + logs

The evidence is API.

## The "wrong scope" anti-pattern

For wrong:
- **Issue:** PII but no Privacy
- **Fix:** Match scope

The scope matches.

## The "observation too early" anti-pattern

For early start:
- **Issue:** Controls not stable
- **Fix:** Wait until stable

The start is after stable.

## The "HR drift" anti-pattern

For drift:
- **Issue:** Terminated, still access
- **Fix:** HR-driven deprovision

The HR is integrated.

## The "vendor SOC 2 only" anti-pattern

For vendor-only:
- **Issue:** Your controls missing
- **Fix:** Complementary

The control is yours.

## The "no change log" anti-pattern

For no log:
- **Issue:** CC8 fail
- **Fix:** Tracked changes

The log is tracked.

## The "single audit" anti-pattern

For one-time:
- **Issue:** Expires
- **Fix:** Always-on

The evidence is continuous.

## The "SOC 2 checklist" pattern

For checklist:
- [ ] Readiness assessment
- [ ] TSCs selected
- [ ] Controls mapped (CC1-CC9)
- [ ] Type 1 first (or Type 2 directly)
- [ ] 9-12 month window
- [ ] Evidence automated
- [ ] HR integrated
- [ ] Change log tracked
- [ ] Subservice documented
- [ ] Annual renewal
- [ ] Privacy if PII

The checklist is 11.

## Verification
- **Test:** Evidence reproducible
- **Test:** Sample 100% of window
- **Test:** All CCs covered
- **Audit:** Quarterly review

## Gotchas
- **The "Type 1 only" anti-pattern.** Plan Type 2.
- **The "screenshots" anti-pattern.** API.
- **The "wrong scope" anti-pattern.** Match.

## Related
- `compliance/iso-27001-compliance.md`
- `compliance/hipaa-compliance.md`
- `compliance/fedramp-compliance.md`
- `compliance/nist-ai-rmf-software-compliance.md`
- `security/audit-log-mandatory.md`
- AICPA: https://www.aicpa-cima.com/topic/audit-assurance/audit-and-assurance-greater-than-soc-2
- AICPA 2024 Reporting Guide: https://www.aicpa-cima.com/resources/download/2024-soc-2-reporting-guide-for-cpa-firms-downloads
- Wikipedia: https://en.wikipedia.org/wiki/Service_Organization_Control
