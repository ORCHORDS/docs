---
title: "WCAG 2.2 Consistent Help Governance"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WCAG 2.2 Consistent Help Governance

## Source

W3C Web Accessibility Initiative — Understanding Success Criterion 3.2.6 Consistent Help: https://www.w3.org/WAI/WCAG22/Understanding/consistent-help

WCAG 2.2 Success Criterion 3.2.6 is Level A. It is concerned with making repeated help mechanisms easier to find across a set of web pages.

## Requirement

When a page includes one of the covered help mechanisms and that mechanism is repeated across multiple pages in the same set, it should occur in the same relative order to other page content unless the user initiates a change that alters the page variation.

Covered mechanisms include:

- human contact details;
- human contact mechanisms;
- self-help options; and
- fully automated contact mechanisms.

The criterion does not require a site to provide a help mechanism. It governs consistency when covered help is provided across multiple pages.

## Governance expectations

- Repeated support and help entry points should have a defined, documented location/order in each page family.
- Responsive variants may differ when the user changes orientation, zoom, or viewport state, but equivalent pages within the same variation should remain consistent.
- Product teams should avoid moving support controls arbitrarily between pages or releases.
- Automated accessibility testing may detect structural drift, but manual review is still required to judge page-set consistency.

## Verification

Sample representative pages from each major page set and verify:

- whether covered help mechanisms are present;
- whether repeated mechanisms occur in a consistent relative order;
- desktop and mobile variants separately;
- keyboard and assistive-technology discoverability; and
- any user-initiated layout-change exception relied upon.

Do not state WCAG conformance solely because this governance document exists.
