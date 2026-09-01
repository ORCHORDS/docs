---
title: "SLSA Source Track Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# SLSA Source Track Governance

## Source assertions

SLSA v1.2 Source requirements are independent of Build levels. Assess the exact Source track version instead of publishing an ambiguous “SLSA level.” The source system must give a durable revision identity and protect change history according to the claimed level. Define the canonical repository URI, revision scheme, branch/tag rules, and the relationship between a reviewed revision and a release input.

A Git commit hash identifies content and parents but does not prove who authorized it or that a protected ref pointed to it. Preserve repository audit events and ref state. Controls must cover direct pushes, force pushes, tag deletion/recreation, merge-queue identities, web edits, imported history, bot tokens, administrator bypass, and repository transfer. Approval rules need an independence definition; two approvals by identities controlled by one automation principal are not independent.

## Concrete verification record

For every release retain: canonical URI; full commit object ID and hash algorithm; protected ref; merge or tag event ID; author and committer identities; required and actual reviewers; policy snapshot; bypass events; and collection timestamp. Bind Build provenance `resolvedDependencies[].uri` and digest to this revision. Do not normalize two mirrors into one identity without a documented equivalence rule.

Test attempts to force-push, delete and recreate a tag, approve one's own change, merge with stale approval, bypass as administrator, alter required status checks, and build from an unprotected SHA. Verify alerts from exported audit events rather than UI screenshots. Repository migrations require a new identity mapping and continuity evidence.

Rollback restores branch/tag protection and revokes bypass credentials, but cannot erase an already consumed malicious revision. Quarantine releases whose source revision traversed an unprotected interval and rebuild only after review. Track protection-setting changes, bypass frequency, noncanonical source URIs, and releases whose provenance revision cannot be matched to the retained source record.

## Sources

- [SLSA v1.2 Source](https://slsa.dev/spec/v1.2/source-requirements)
- [SLSA tracks](https://slsa.dev/spec/v1.2/levels)
