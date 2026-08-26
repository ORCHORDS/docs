---
title: "Backup Policy"
owner: "Operations Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Backup Policy

## Purpose

Define backup expectations for information and configurations where loss would create material business, legal, security, or recovery impact.

## Requirements

Backup design SHOULD define scope, frequency, retention, protection, ownership, integrity verification, restoration method, and deletion obligations.

Backups must receive protection appropriate to the sensitivity of the data they contain. A backup is not useful evidence of recoverability until restoration has been tested.

## Resilience

Where risk warrants it, backups should reduce common-mode failure through separation of credentials, administrative paths, technology, or location.

## Lifecycle

Backup retention must align with data-retention and legal-hold requirements. Obsolete backup sets should be disposed of securely.

See [Backup and Restore SOP](../sop/BACKUP_RESTORE_SOP.md).
