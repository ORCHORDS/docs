---
title: "Source Control Policy"
owner: "Engineering Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Source Control Policy

## Purpose

Protect source integrity, accountability, and reviewability.

## Requirements

- Material changes MUST be committed to version control.
- Protected branches SHOULD reject direct, unreviewed changes.
- Force-push to protected history SHOULD be disabled.
- Changes to high-impact areas SHOULD require approval from a second trusted
  person.
- Required checks SHOULD be enforced by the source-control platform rather
  than documented as manual expectations only.
- Administrative bypasses MUST be limited, logged where supported, and used
  only for justified exceptions or emergencies.
- Signed commits or tags MAY be required for release-critical workflows when
  they provide meaningful assurance in the chosen platform.

These controls are consistent with the direction of SLSA 1.2 Source Track,
which emphasizes preserved history, enforced technical controls, provenance,
and two-party review at higher assurance levels.

## Pull requests

A pull request should state:

- what changes;
- why;
- risk;
- verification performed;
- rollout and rollback considerations when applicable;
- documentation changes;
- security or privacy implications.

## Branches

Use short-lived branches where practical. Branch names should be descriptive
and avoid confidential information.

## History

Do not rewrite shared protected history to hide mistakes. Correct mistakes with
new commits or an approved repository-administration procedure so the audit
trail remains intelligible.
