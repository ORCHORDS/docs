---
title: "WCAG 2.2 Target Size Governance"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WCAG 2.2 Target Size Governance

## Purpose

Define a public-safe review control for WCAG 2.2 Success Criterion 2.5.8, Target Size (Minimum).

Primary source: https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html

## Requirement baseline

WCAG 2.2 adds Target Size (Minimum) at Level AA. The general minimum target size is 24 by 24 CSS pixels unless one of the criterion's defined exceptions applies.

This requirement is not satisfied merely because an element is visually large. The actionable target area and spacing relationship to adjacent targets matter.

## Review control

For interactive controls:

- measure the actual pointer target, not only visible artwork;
- check dense toolbars, icon buttons, inline links, pagination, dismiss controls, and compact mobile actions;
- document any reliance on a WCAG exception;
- verify zoom and responsive layouts do not collapse spacing into accidental target overlap;
- test representative touch and pointer interaction, not only automated accessibility scans.

## Evidence

A review record should identify:

- tested page or component;
- viewport or responsive state;
- target dimensions or spacing evidence when relevant;
- applicable exception, if any;
- remediation owner and status for failures.

## Claims boundary

Passing this control alone does not establish WCAG 2.2 conformance. Accessibility claims require evidence across all applicable success criteria and cannot rely solely on automated scanning.

## Related

- [Accessibility Testing](ACCESSIBILITY_TESTING.md)
- [Mobile Accessibility Governance](MOBILE_ACCESSIBILITY.md)
- [Accessibility Release Gate](ACCESSIBILITY_RELEASE_GATE.md)
- [WCAG 2.2 Change Control](WCAG_2_2_CHANGE_CONTROL.md)
