---
title: "WCAG 2.2 Focus Not Obscured (Minimum)"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# WCAG 2.2 Focus Not Obscured (Minimum)

## Normative target
WCAG 2.2 Recommendation, Success Criterion **2.4.11**, is **Level AA**. When a user interface component receives keyboard focus, author-created content must not hide the component entirely. The criterion is deliberately “minimum”: partial visibility passes. SC 2.4.12 is the separate Level AAA requirement for complete visibility. Content opened by the user can cover focus without failing 2.4.11; examples include an expanded submenu or non-modal dialog. User-agent chrome and software keyboards are outside “content made by the author.”

The unit under test is the focused component, not merely its focus indicator. A button whose outline peeks out from beneath a sticky footer while the button itself is entirely covered fails. Conversely, a component partly visible behind a fixed header can satisfy 2.4.11 even if it would fail 2.4.12.

## Implementation patterns
Set `scroll-padding-block-start` on scrolling containers to the occupied height of persistent headers and `scroll-padding-block-end` for persistent footers. Give programmatically focused validation targets `scroll-margin`. When opening an author-controlled panel, either move focus into it or reposition/dismiss it before advancing focus behind it. Avoid fixed cookie banners that remain over the tab sequence; reserve layout space or provide a dismissal control early in focus order.

Nested scrollers need independent offsets. A browser scrolling the document cannot expose a control hidden inside an unscrolled grid. Virtualized lists must render and scroll the focused row before assigning focus. Do not “fix” the issue by setting positive `tabindex` or suppressing focus.

## Concrete test
Test each responsive breakpoint at 100%, 200%, and 400% zoom. Open all persistent author overlays, then Tab and Shift+Tab through every component, including controls revealed by validation, menus, dialogs, and sticky table regions. At each stop, capture the focused element’s bounding rectangle and rectangles of author-created overlays. Fail only when overlay union covers the entire focused component. Repeat after direct fragment navigation and scripted focus. Record whether each covering layer was user-opened, because that exception changes the result.

## Evidence and failure signatures
Retain viewport size, zoom, DOM path, focus order, overlay geometry, screenshot, and keyboard action. Typical failures are sticky headers after anchor focus, consent banners hiding checkout controls, and nested overflow containers that do not react to focus. An automated intersection calculation is useful, but manually confirm stacking, clipping, transforms, and translucent layers.

## Sources
- [WCAG 2.2 Recommendation — SC 2.4.11](https://www.w3.org/TR/WCAG22/#focus-not-obscured-minimum)
- [Understanding SC 2.4.11](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html)
