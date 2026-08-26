# Content-driven breakpoints are component contracts

**Issue**

Breakpoints named after phones, tablets, or desktops encode a temporary device catalog. A reusable layout should change when its content can no longer satisfy readable measure, target spacing, and component constraints.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Define each breakpoint beside the component invariant it protects, such as minimum control width or maximum readable line length.
- Prefer intrinsic layout with grid, flexbox, min/max/clamp, and container queries before adding viewport thresholds.
- Keep container and media query units explicit and test browser zoom because CSS pixels are not hardware pixels.
- Document boundary ownership: component containers govern local composition; viewport queries govern true viewport features.
- Do not branch server output by guessed device class when one semantic document can adapt in CSS.

## Verification

1. Capture just below, exactly at, and just above every threshold.
2. Repeat at 200% and 400% zoom, with long translations, large text, and reduced available width.
3. Nest components in narrow and wide containers independent of the viewport.
4. Assert no clipped content or two-dimensional scrolling where WCAG reflow applies.

## Gotchas

- A breakpoint that only matches a screenshot width has no durable contract.
- Container query thresholds depend on containment and the actual containing box.
- Orientation is a viewport relationship, not a reliable physical-device posture.

## Official sources

- [W3C Media Queries Level 5](https://www.w3.org/TR/mediaqueries-5/)
- [W3C CSS Containment Level 3](https://www.w3.org/TR/css-contain-3/)
- [WCAG 2.2 Reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html)
