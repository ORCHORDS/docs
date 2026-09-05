# Interval Budget Review Playbook

## Purpose

A periodic review of inspection, scanning, refresh, rotation, and revocation intervals to balance assurance, cost, and risk. Used when an organization operates many systems with overlapping cryptographic, identity, vulnerability, and patching timers.

## Procedure

1. Enumerate the timer families in scope: key rotation, certificate renewal, vulnerability scan, signature refresh, dependency update, access review, backup verification, retention expiry.
2. For each timer family, record the current interval, the policy-required interval, the operational cost per cycle, and the residual risk per cycle.
3. Classify each timer family as: too long (risk > appetite), too short (cost > benefit), or aligned.
4. Adjust intervals only when there is a documented basis: regulator mandate, vendor EOL, threat intel, observed compromise, or cost benefit analysis.
5. Confirm each timer has an assigned owner, an automated trigger where possible, and an escalation path on missed execution.
6. Confirm timers do not collide with maintenance windows or with each other in ways that degrade reliability.
7. Re-run the review at the cadence defined by the governance policy (quarterly minimum for high-risk timer families).
8. Record changes in the cryptographic and operational inventory with effective dates.

## Source basis

- NIST SP 800-57 Pt. 1 Rev. 5 — Recommendation for Key Management.
- NIST SP 800-131A Rev. 2 — Cryptographic Algorithm and Key Length Transition.
- NIST SP 800-218A — Secure Software Development Framework for Generative AI (touches update cadence).
- FFIEC, PCI DSS 4.0, and SOC 2 Trust Service Criteria for cross-mapped controls.
