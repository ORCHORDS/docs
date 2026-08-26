# Verified remediation closure evidence

**Issue:** Remediation work is often closed when a patch merges, even though the vulnerable artifact may remain deployed, unsupported branches may be missed, or the control may not prevent recurrence.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Lesson

“Code merged” is an implementation milestone, not closure. Close a vulnerability or corrective action only after evidence shows the risk is removed or explicitly accepted across the affected scope.

## Closure contract

Every remediation issue should define before work starts:

- affected repositories, versions, artifacts, environments, and customers;
- a test or observation that demonstrates the unsafe condition;
- the target fixed state;
- rollout and rollback expectations;
- evidence owner and reviewer;
- recurrence-prevention action;
- residual-risk approval and expiry when full remediation is impossible.

## Evidence sequence

1. Preserve a safe reproduction or scanner finding.
2. Link the reviewed code change to the issue without publishing sensitive exploit details.
3. Produce fixed artifacts from the reviewed revision.
4. Verify artifact identity, signature/provenance where available, and deployment inventory.
5. Rerun the original detection and a negative/abuse test.
6. Check supported release branches and variants.
7. Monitor for regression during an appropriate observation window.
8. Have someone other than the implementer review the evidence for high-impact findings.
9. Close with a concise evidence summary and create separately owned prevention work if it cannot be completed immediately.

## Operational prioritization

CISA’s Known Exploited Vulnerabilities catalog is a living signal of active exploitation. When an affected component enters the catalog, raise priority and use the catalog due date as a strong external scheduling input. BOD 22-01 binds US federal civilian agencies; other organizations should not misstate that legal scope, though CISA urges broader prioritization.

## Checks

- Reopen automatically if deployment inventory still shows the vulnerable version.
- Track mean time from merge to verified deployment, not only time to merge.
- Sample closed items and reproduce the closure evidence.
- Expire risk acceptances and exceptions rather than closing them permanently.

## Gotchas

- Scanner disappearance can result from inventory loss or suppression.
- A compensating control needs an effectiveness test.
- Do not attach secrets, customer data, or weaponized proof-of-concept material to ordinary issues.

## Sources

- [CISA Known Exploited Vulnerabilities Catalog](https://www.cisa.gov/known-exploited-vulnerabilities-catalog)
- [CISA explanation of KEV remediation prioritization and BOD 22-01 scope](https://www.cisa.gov/news-events/alerts/2025/03/31/cisa-adds-one-known-exploited-vulnerability-catalog)
- [NIST SP 800-218, Secure Software Development Framework](https://csrc.nist.gov/pubs/sp/800/218/final)
