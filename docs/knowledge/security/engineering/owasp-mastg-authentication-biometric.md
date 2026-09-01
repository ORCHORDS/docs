---
title: "OWASP MASTG 2.0 Authentication and Biometrics"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# OWASP MASTG 2.0 Authentication and Biometrics

## Pinned source and scope
OWASP MASTG **2.0.0** authentication testing mapped to **MASVS-AUTH**. This article uses the named version and identifiers; do not combine evidence from another edition without a migration record.

## Control interpretation
Separate server authentication, local biometric gating, key use authorization, session persistence, and recovery. A successful biometric prompt authenticates the device user locally; it does not by itself authorize a server operation. Configure whether device credential fallback is allowed and whether biometric enrollment changes invalidate protected keys.

## Domain-specific procedure
Cancel prompts, background during prompt, lock/unlock, add or remove biometrics, change device credential, reboot, restore backup, hook local success callbacks on a test device, replay server tokens, expire sessions, switch accounts, and test offline mode. Confirm sensitive operations require fresh server authorization where the threat model demands it and logout removes all account-bound material.

## Evidence and decision
Retain prompt policy, enrollment state, key attributes, callback traces, server-token lifecycle, account state, and results for every cancellation and fallback path. Distinguish local bypass from server impact.

## Failure modes
UI-only biometric gates, reusable tokens after logout, insecure device-credential fallback, and account material surviving user switches are failures.

## Sources
- [Pinned canonical source](https://mas.owasp.org/MASTG/)
