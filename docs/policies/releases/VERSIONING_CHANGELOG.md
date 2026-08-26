---
title: "Versioning and Changelog Policy"
owner: "Release Manager"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "180 days"
next-review: "2027-02-18"
---

# Versioning and Changelog Policy

## Versioning

Use Semantic Versioning 2.0.0 when public compatibility is meaningfully
described by major/minor/patch versions. Do not force semantic versioning onto
assets where it does not convey compatibility.

## Release identifiers

Release identifiers should be immutable once published. Do not silently
replace artifacts under the same version.

## Changelog

User-facing changelogs should:

- explain material changes in user terms;
- distinguish security fixes when disclosure is safe;
- identify breaking changes and migration needs;
- avoid internal ticket dumps and implementation noise;
- link to detailed guidance when users must take action.

## Corrections

If published notes are wrong, correct them transparently. Material corrections
should indicate what changed and when.

## Security

Coordinate disclosure timing for security-sensitive fixes with the
vulnerability-management process.
