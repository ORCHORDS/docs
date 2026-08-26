---
title: "Business Continuity and Recovery Policy"
owner: "Operations Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "180 days"
next-review: "2027-02-18"
---

# Business Continuity and Recovery Policy

## Purpose

Ensure critical business capabilities can continue or recover from disruptive
events.

## Requirements

Critical capabilities should define:

- business owner;
- dependencies;
- maximum tolerable outage or disruption;
- recovery-time objective (RTO) where appropriate;
- recovery-point objective (RPO) where data loss matters;
- backup or alternate-operation strategy;
- restoration priority;
- communication path;
- recovery test cadence.

## Backups

- Protect backups from the same failure or compromise as primary data where
  practical.
- Restrict backup access.
- Monitor backup completion and integrity.
- Retain backups according to business, legal, and security needs.
- Test restoration at a cadence justified by criticality.

A successful backup job is not evidence that recovery works; a verified restore
is stronger evidence.

## Exercises

Use table-top exercises and technical recovery tests to validate assumptions.
Material failures create tracked corrective actions with owners and due dates.

Follow [Backup and Restore SOP](../sop/BACKUP_RESTORE_SOP.md).
