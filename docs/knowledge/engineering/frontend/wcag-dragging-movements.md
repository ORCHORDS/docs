---
title: "WCAG 2.2 Dragging Movements"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# WCAG 2.2 Dragging Movements

## Requirement
SC **2.5.7 Dragging Movements** is **Level AA**. Functionality that uses a dragging movement must also be achievable with a single pointer without dragging, unless dragging is essential or the functionality is determined by the user agent rather than the author. “Single pointer” includes mouse, stylus, touch, and head pointer. Keyboard support alone does not meet this pointer requirement.

Dragging means a down event, movement while held, and release where the movement path or endpoints affect the outcome. The criterion does not ban drag-and-drop. It requires an equivalent path-independent operation. Freehand drawing can be essential; sorting cards usually is not. Native HTML range input behavior is user-agent controlled, but an author-built slider is not automatically exempt.

## Alternatives by interaction
For sortable lists, expose Move up/Move down buttons or a destination menu. For Kanban, “Move to column…” plus position selection must reach every valid result. For maps, provide address or coordinates fields and zoom buttons. For crop tools, numeric bounds or increment controls must preserve precision. For sliders, tapping a point on the track may be a single-pointer alternative; plus/minus buttons are clearer and easier to test.

Keep alternatives visible to pointer users, label them, preserve focus after movement, and announce the changed position through ordinary text or an appropriate live region. Do not require a long press followed by movement—that is still path-dependent.

## Test protocol
Inventory handlers using pointer capture, `dragstart`, pointer movement, touch movement, and sortable libraries. For every business outcome produced by drag, attempt the same outcome using one pointer with discrete clicks or taps and no held movement. Test minimum, maximum, arbitrary middle positions, cancellation, scrolling, zoom, and reordering first/last items. Verify the alternative does not reveal fewer destinations or lose precision.

Record the original drag gesture, alternative sequence, final persisted state, input device, and screen recording. Fail if only keyboard controls exist, if the alternative is hidden until a drag begins, or if it supports only common destinations. Document any essential exception with why path movement is intrinsic rather than merely convenient.

## Sources
- [WCAG 2.2 — SC 2.5.7](https://www.w3.org/TR/WCAG22/#dragging-movements)
- [Understanding Dragging Movements](https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements.html)
