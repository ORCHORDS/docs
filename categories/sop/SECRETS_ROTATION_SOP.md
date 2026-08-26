---
title: "SOP: Secrets Rotation"
owner: "Security Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# SOP: Secrets Rotation

## Trigger

Use for suspected exposure, personnel or supplier access change, cryptographic
or policy requirement, or scheduled rotation where required.

## Procedure

1. Identify affected secret and owner without copying the secret into the
   record.
2. Determine where it is used and what will fail if revoked.
3. Create or activate replacement material through an approved mechanism.
4. Update authorized consumers.
5. Revoke or disable old material as soon as safely practical.
6. Verify expected services operate using the replacement.
7. Check logs and records for continued old-secret use.
8. Preserve incident evidence when exposure is suspected.
9. Close after old material is unusable and consumers are confirmed.

Never paste real secret values into the rotation record.
