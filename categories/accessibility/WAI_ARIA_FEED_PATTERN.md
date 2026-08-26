---
title: "WAI-ARIA Feed Pattern"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WAI-ARIA Feed Pattern

## Purpose

Provide guidance for dynamic, progressively loaded streams of article-like content.

## Pattern baseline

A feed is a page structure that can load additional articles as users navigate or scroll. It differs from many widgets because assistive technologies commonly interact with it in reading mode.

## Guidance

- Use role `feed` on the container when the APG pattern is appropriate.
- Represent each feed item as an `article` with an accessible name or description where needed.
- Preserve stable focus and reading position while adding or removing items.
- Ensure loading additional content does not trap keyboard or assistive-technology users.
- Avoid relying on pointer scrolling as the only way to reach newly loaded content.

## Verification

Test reading-mode navigation, keyboard movement, dynamic loading, focus preservation, and announcements with representative screen readers.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Feed Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/feed/
