---
title: "SOP: Backup and Restore"
owner: "Operations Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "180 days"
next-review: "2027-02-18"
---

# SOP: Backup and Restore

## Purpose

Verify that critical data can be recovered, not merely that backup jobs report
success.

## Procedure

1. Select the data set and recovery objective to test.
2. Confirm the test will not overwrite or expose production data.
3. Identify the backup generation and expected recovery point.
4. Restore into an isolated or approved recovery location.
5. Validate integrity, completeness, permissions, and application usability.
6. Measure actual recovery time and data-loss window.
7. Compare results with stated RTO/RPO expectations.
8. Record defects and remediation owners.
9. Remove test data securely when no longer needed.
10. Escalate a failed critical restore as an operational risk.

## Evidence

Record backup identifier/date, restore date, tester, validation performed,
measured recovery time, measured recovery point, result, and follow-up.
