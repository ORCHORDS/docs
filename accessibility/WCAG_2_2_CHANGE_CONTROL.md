---
title: "WCAG 2.2 Change Control"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WCAG 2.2 Change Control

## Purpose

Provide a public-safe review checklist for changes introduced by WCAG 2.2 without implying that any ORCHORDS product, service, or website has been certified or independently assessed for WCAG conformance.

## Current standards baseline

W3C published WCAG 2.2 as a W3C Recommendation on 5 October 2023. W3C identifies nine success criteria added since WCAG 2.1 and notes that Success Criterion 4.1.1 Parsing is obsolete and removed from WCAG 2.2.

The new WCAG 2.2 success criteria are:

- 2.4.11 Focus Not Obscured (Minimum) — Level AA.
- 2.4.12 Focus Not Obscured (Enhanced) — Level AAA.
- 2.4.13 Focus Appearance — Level AAA.
- 2.5.7 Dragging Movements — Level AA.
- 2.5.8 Target Size (Minimum) — Level AA.
- 3.2.6 Consistent Help — Level A.
- 3.3.7 Redundant Entry — Level A.
- 3.3.8 Accessible Authentication (Minimum) — Level AA.
- 3.3.9 Accessible Authentication (Enhanced) — Level AAA.

## Change-review requirements

When a public-facing interface is created or materially changed, accessibility review should explicitly consider the WCAG 2.2 additions that apply to that interface rather than assuming older WCAG 2.0 or 2.1 test coverage is sufficient.

At minimum, reviewers should check whether:

1. Keyboard focus can become obscured by sticky headers, banners, dialogs, drawers, cookie notices, or other author-created content.
2. Drag-only interactions have an alternative that does not require dragging when WCAG 2.5.7 applies.
3. Pointer targets satisfy WCAG 2.5.8 or a documented exception in the criterion applies.
4. Repeated help mechanisms retain a consistent relative order across the relevant set of pages.
5. Multi-step processes avoid unnecessary re-entry of information previously supplied in the same process, subject to the criterion's exceptions.
6. Authentication flows do not introduce prohibited cognitive-function tests and support mechanisms permitted by WCAG 2.2, such as password managers and copy/paste, where the criterion applies.
7. Test evidence distinguishes Level A, AA, and AAA criteria rather than presenting AAA guidance as a general conformance requirement.

## Evidence expectations

A review record should identify:

- the interface and version reviewed;
- the WCAG version and conformance level used as the target;
- applicable success criteria and any documented exceptions;
- manual keyboard and interaction results;
- assistive-technology coverage where relevant;
- defects, owners, and remediation status;
- the date of the evidence.

Automated tooling can support testing but does not, by itself, establish WCAG conformance.

## Claims boundary

Do not publish statements such as "WCAG 2.2 compliant," "fully accessible," or equivalent assurance unless current evidence supports the exact scope and claim. This document defines a review control; it is not evidence that a particular ORCHORDS property conforms.

## Primary sources

- W3C, Web Content Accessibility Guidelines (WCAG) 2.2: https://www.w3.org/TR/WCAG22/
- W3C WAI, What's New in WCAG 2.2: https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/
- W3C WAI, Understanding WCAG 2.2: https://www.w3.org/WAI/WCAG22/Understanding/
