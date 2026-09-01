# CSS Anchor Positioning Dialog Popover

## Scope

Using CSS anchor positioning to place a popover or dialog relative to an invoking element without JavaScript positioning loops. Covers the popover attribute and `showPopover()` path on the HTML side, the CSS anchor properties (`anchor-name`, `position-anchor`, `position-area`, `position-try-fallbacks`) on the styling side, and the interactions between the two models. Excludes cross-origin anchoring, custom anchor element resolution via the `anchor()` function in inset properties, and advanced fallback chains beyond what a dialog-on-button use case needs. Also excludes framework wrappers; the same model applies in any stack but the examples are framework-free.

## Workflow or implementation guidance

The recurring problem: a "open filter panel" button at the bottom of a table needs a popover that grows upward from the button, clamps inside the viewport, and closes on outside click. Historically this required a resize/scroll listener that repositioned a fixed-position element, with all the tearing and lifecycle bugs that entails. Anchor positioning moves the geometry into CSS.

Mark the popover content as a popover so the browser supplies top layer promotion, light dismiss, and focus behavior.

```html
<button id="filter-btn" class="btn">Filters</button>
<div id="filter-pop" popover class="filter-pop">
  <!-- controls -->
</div>

<script>
  const btn = document.getElementById('filter-btn');
  const pop = document.getElementById('filter-pop');
  btn.addEventListener('click', () => pop.showPopover());
</script>
```

Give the button an anchor name and the popover a matching anchor reference. Anchor names are identifiers, so the dotted-quoted form `--filter` works as a custom-ident-like name and the same name must be referenced in `position-anchor`.

```css
#filter-btn { anchor-name: --filter; }

.filter-pop {
  position: fixed;
  position-anchor: --filter;
  position-area: top span-right;
  margin: 8px;
}
```

`position-area: top span-right` resolves the popover above the anchor, letting it span to the right of the anchor's inline position without hardcoding pixel offsets. The reserved viewport insets from the popover's default styling are already handled by the popover UA styles, so only the offset margin is needed.

For a modal dialog variant, use `<dialog>` with `showModal()` instead of the popover attribute. Dialogs do not get light dismiss, which is what you want when the dialog collects a required choice. Anchor positioning applies the same way: set `position: fixed`, `position-anchor`, and a `position-area` on the `dialog[open]` state.

Fallback for a popover that would clip at the viewport top is a one-line property.

```css
.filter-pop {
  position-try-fallbacks: flip-block, flip-inline;
}
```

When the primary placement would overflow, the browser re-resolves the position-area against the alternate placements before painting, so there is no flash of a mispositioned element.

Close and reopen semantics stay in DOM code: `hidePopover()` from a "Apply" button, `beforetoggle` on the popover for analytics, and the light-dismiss path for everything else. No scroll or resize listeners are needed because the anchor relationship is declarative; the browser recomputes geometry when either the anchor or the viewport changes.

## Controls

- `popover` attribute plus `showPopover()` / `hidePopover()` / `togglePopover()` control top layer and dismissal.
- `anchor-name` on the invoking element; must be a valid custom ident and globally unique per document.
- `position-anchor` on the popover referencing that name; mismatch means the popover falls back to static positioning.
- `position-area` selects the placement region relative to the anchor; `span-*` keywords let the popover extend across the anchor's inline axis.
- `position-try-fallbacks` lists alternate placements attempted in order when the primary placement overflows.
- `beforetoggle` and `toggle` events on the popover are the hooks for measuring open/close latency and lazy-attaching heavy content.

## Validation evidence

- Render the button near each viewport edge and confirm the popover flips rather than clips; screenshot-diff the four placements in CI.
- Tab into the page and confirm focus moves into the popover on open and returns to the button on close (popover focus behavior, verified manually and with an automated focus-order assertion).
- Confirm `getComputedStyle(pop).positionAnchor` resolves to the anchor name after styles load; a resolved value plus a non-zero `getBoundingClientRect` gap between button top and popover bottom is direct evidence the anchor link is live.
- Confirm no `scroll`/`resize` listeners remain attached to the document once the feature ships; their removal is the point of the migration.

## Failure modes and correction

- Anchor name typo or the anchor element inside a different containing block than expected: the popover renders at its static position. Fix by checking the resolved `position-anchor` value and ensuring the popover is a positioned element (`position: fixed` or `absolute`).
- Popover placed relative to a scrolling container but with `position: fixed`: it will not track scroll inside the container. Anchor positioning with fixed positioning resolves against the viewport, so switch to a `position: absolute` popover anchored within the scroll container, or restructure so the anchor is viewport-stable.
- Fallback flips aggressively on small viewports, oscillating during window resize. Add explicit fallback order ending in a centered placement, and prefer one fallback keyword chain over several competing rules.
- Popover content taller than the viewport: `position-area` alone will not scroll. Add `max-height` with `overflow: auto` on the popover body, since the top layer element still respects its own box constraints.
- Overlay stacking regressions: popovers and modal dialogs both use the top layer; opening a dialog from a popover closes the popover via light dismiss. If both must stay open, use a non-modal pattern rather than fighting the dismissal rules.

## Limitations

- Browser support for the anchor positioning properties is limited to recent Chromium-based browsers; Firefox has been shipping progressively. A `@supports (anchor-name: --a)` guard plus the legacy JS positioning path must be kept for the transition period.
- Anchors and positioned elements must be in the same document; you cannot anchor a popover inside a closed shadow root to an outside element without exposing the name through the shadow boundary.
- The implicit anchor (the invoking element) is available for the popover element itself, but relying on explicit `anchor-name` is more predictable when the same popover is invoked from several buttons.
- `anchor()` function usage in arbitrary inset properties offers more precision than `position-area` but is a larger surface; this document intentionally stays with the simpler model.
- Animating between fallback placements is not covered by `position-try-fallbacks`; transitions on the geometry itself are not interpolated.

## Canonical sources

- WHATWG, HTML Standard, popover: https://html.spec.whatwg.org/multipage/popover.html
- CSS Working Group, CSS Anchor Positioning Module Level 1: https://drafts.csswg.org/css-anchor-position-1/
- MDN, Popover API overview: https://developer.mozilla.org/en-US/docs/Web/API/Popover_API
- MDN, `anchor-name`: https://developer.mozilla.org/en-US/docs/Web/CSS/anchor-name
