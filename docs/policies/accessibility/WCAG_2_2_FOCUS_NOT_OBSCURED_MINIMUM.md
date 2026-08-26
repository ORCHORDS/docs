---
title: "WCAG 2.2 Focus Not Obscured Minimum"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WCAG 2.2 Focus Not Obscured (Minimum)

Source: https://www.w3.org/TR/WCAG22/#focus-not-obscured-minimum

WCAG 2.2 Success Criterion 2.4.11 is Level AA. When a user-interface component receives keyboard focus, it must not be entirely hidden by author-created content.

## Governance

- Test sticky headers, sticky footers, cookie notices, chat launchers, drawers, dialogs, and other overlays against keyboard focus paths.
- A component being programmatically focused is insufficient if the user cannot see any part of it.
- Content opened by the user may obscure focus where the WCAG exception applies; document the tested interaction rather than assuming every overlay is exempt.
- Accessibility testing must include real keyboard traversal at supported viewport sizes.

## Evidence

Keep reproducible test steps and issue evidence for failures. Automated checks alone do not prove this success criterion because visibility depends on layout and interaction state.

This document defines the control expectation; it does not by itself claim product conformance.