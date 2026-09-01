---
title: "NIST SP 800-115 Technical Security Testing Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# NIST SP 800-115 Technical Security Testing Governance

## Publication and scope

This article operationalizes **NIST Special Publication 800-115, Technical Guide to Information Security Testing and Assessment**. It describes governance evidence and decisions; it does not make the publication mandatory or claim certification. Applicability depends on the organization, system, contract, and legal context.

## Planning, test techniques, and reporting

SP 800-115 distinguishes review techniques, target identification and analysis techniques, and target vulnerability validation techniques. Examples include documentation and log review, ruleset and configuration review, network discovery, port and service identification, vulnerability scanning, password cracking, penetration testing, and social engineering. Its penetration testing model uses planning, discovery, attack, and reporting phases.

## Publication-specific workflow

Authorize the test in writing; define systems, exclusions, source addresses, hours, data handling, stop conditions, contacts, and incident coordination. Select techniques proportional to risk. Validate automated findings. During penetration testing, preserve the path from discovery through attempted exploitation and privilege escalation. Report technical facts, business consequence, limitations, and corrective priorities; then retest.

Assign named owners for each decision and define review triggers. Tailor implementation to mission impact and architecture, but preserve the publication's named concepts so reviewers can trace local practice back to the source. Document assumptions, exclusions, inherited capabilities, and residual risk rather than presenting partial coverage as full implementation.

## Evidence to retain

Retain rules of engagement, signed authorization, asset list, tester identities, tool versions and configurations, synchronized timestamps, command logs, packet or scanner output, validation notes, exploit path, captured-data handling record, findings, remediation tickets, and retest evidence.

Evidence must identify scope, collection date, source, owner, and covered population. Preserve raw results separately from interpretation. When remediation occurs, retain the original finding and append verification rather than rewriting history.

## Review and metrics

Review after material system, supplier, threat, mission, or organizational changes and at the stated document cycle. Metrics must include denominators and blind spots. Track overdue high-impact decisions, evidence age, exceptions approaching expiry, failed tests, and time to verified closure. Management review should focus on consequences and unresolved risk, not a context-free completion percentage.

## Failure modes

Never scan or exploit outside authorization. Do not confuse a scanner finding with validated exposure, conceal destructive side effects, use production credentials carelessly, omit negative coverage, or publish sensitive exploit details beyond need-to-know.

Also avoid unsupported claims based only on policy text, a product purchase, or one convenience sample. If evidence is unavailable, record the unknown, affected scope, interim safeguard, accountable owner, and decision deadline.

## Primary Sources

- [NIST Special Publication 800-115, Technical Guide to Information Security Testing and Assessment](https://csrc.nist.gov/pubs/sp/800/115/final)
