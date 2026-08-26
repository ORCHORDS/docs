---
title: "WAI-ARIA Treegrid Pattern"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WAI-ARIA Treegrid Pattern

## Purpose

Provide public implementation guidance for hierarchical interactive data grids using the WAI-ARIA Authoring Practices Guide treegrid pattern.

## Pattern baseline

A treegrid combines hierarchical tree behavior with a grid. Rows may contain child rows that can be expanded or collapsed, while rows and cells remain navigable as interactive tabular content.

## Semantics

- expose the widget with `role="treegrid"` when native table semantics alone are insufficient;
- use row and cell/header roles appropriate to the content;
- expose expansion state on parent rows or the controlling element;
- provide an accessible name for the treegrid;
- expose row/column counts and indexes when virtualization means not all content is present in the DOM;
- expose read-only and sort states when those features apply.

## Implementation guidance

- Keep hierarchical relationships and visible indentation aligned.
- Ensure every cell users need to perceive in application-style navigation can receive or contain focus.
- Distinguish row expansion, focus, editing, and selection state.
- Preserve predictable directional navigation as rows expand or collapse.
- Test virtualized and dynamically loaded rows carefully with assistive technologies.

## Verification

Confirm that users can navigate the hierarchy and cells, expansion state is accurate, hidden descendants are unavailable, row and column position information remains meaningful, and editable cells expose correct read-only state when editing is unavailable.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Treegrid Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/treegrid/
