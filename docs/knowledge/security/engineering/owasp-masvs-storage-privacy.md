---
title: "OWASP MASVS 2.1 Storage and Privacy Verification"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# OWASP MASVS 2.1 Storage and Privacy Verification

## Pinned source and scope
OWASP MASVS **2.1.0**, groups **MASVS-STORAGE** and **MASVS-PRIVACY**. This article uses the named version and identifiers; do not combine evidence from another edition without a migration record.

## Control interpretation
Inventory credentials, personal data, identifiers, cryptographic material, and derived metadata across databases, preferences, files, caches, logs, backups, notifications, screenshots, pasteboards, analytics, crash reports, and interprocess transfers. Apply minimization and platform protected storage; encryption does not justify unnecessary retention.

## Domain-specific procedure
Exercise login, backgrounding, notifications, crashes, sharing, logout, account deletion, and backup/restore. Search application containers, system logs, screenshots/task snapshots, pasteboard, backup archives, analytics requests, and crash payloads. Verify deletion and retention windows, not just UI disappearance. Record device lock state and whether hardware-backed key protection is actually configured.

## Evidence and decision
Retain before/after container inventories, backup manifests, log extracts, network telemetry, retention timestamps, and key-protection attributes. Redact values while preserving locations and classifications.

## Failure modes
Database encryption alongside plaintext logs, sensitive task snapshots, undeleted analytics identifiers, and backup-restored tokens are failures.

## Sources
- [Pinned canonical source](https://mas.owasp.org/MASVS/03-Using_the_MASVS/)
