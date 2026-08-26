---
title: "WAI-ARIA Breadcrumb Pattern"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WAI-ARIA Breadcrumb Pattern

## Purpose

Provide public implementation guidance for breadcrumb navigation using the WAI-ARIA Authoring Practices Guide breadcrumb pattern.

## Pattern baseline

A breadcrumb trail presents links to parent pages of the current page in hierarchical order and helps users understand their position within a site or application.

Accessible implementations should:

- place the breadcrumb trail inside a navigation landmark;
- give the landmark a meaningful accessible label with `aria-label` or `aria-labelledby`;
- represent the hierarchy as a list where appropriate;
- mark the current page link with `aria-current="page"`;
- omit `aria-current` when the current-page item is rendered as non-link text unless there is a specific need for it.

## Keyboard interaction

No special keyboard model is required. Breadcrumb links follow ordinary link keyboard behavior and the normal document tab order.

## Implementation guidance

1. Use concise, meaningful link text for each hierarchy level.
2. Do not expose decorative separators such as chevrons as meaningful content to assistive technology.
3. Keep the current-page state synchronized with navigation state.
4. Avoid using breadcrumb navigation as the only indication of the current page.
5. Ensure the landmark label distinguishes the breadcrumb from other navigation landmarks on the same page.

## Verification

Confirm that each linked ancestor is keyboard reachable, the trail is exposed as navigation, the current page is correctly identified, separators do not create noisy announcements, and link destinations match the visible hierarchy.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Breadcrumb Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/breadcrumb/
