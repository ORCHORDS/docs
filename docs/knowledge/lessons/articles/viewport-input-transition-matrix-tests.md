# Responsive tests need a viewport-input-transition matrix

**Issue**

A few fixed phone and desktop screenshots miss failures caused by resize, rotation, split-screen, fold-like segmentation, zoom, and capability changes after initial render.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Define orthogonal axes for viewport dimensions, device scale factor, input capabilities, keyboard, zoom/text scale, orientation, and reduced preferences.
- Select pairwise coverage for routine CI and reserve full boundary/state-transition coverage for critical components.
- Test transitions without reloading: resize, rotate, attach input, enter split-screen width, and restore.
- Assert semantic invariants—focus, accessible name, control reachability, preserved draft state—alongside screenshots.
- Use named projects for stable environment contracts, but add exact breakpoint-boundary cases with `page.setViewportSize()`.

## Verification

1. For every breakpoint run below/equal/above widths in both initial-load and live-resize paths.
2. Keep focus inside the same logical control through layout recomposition.
3. Test pointer and keyboard activation at narrow and wide widths rather than coupling one input to each width.
4. Include scroll position, open dialogs, virtual keyboard-sized viewport changes, and interrupted network activity during transitions.

## Gotchas

- Playwright viewport emulation does not reproduce every physical browser or fold posture.
- Changing viewport size does not automatically change screen size or input media features.
- Screenshot success can coexist with lost focus or unreachable controls.
- Rotation and resize handlers can race with animation and network state.

## Official sources

- [Playwright emulation](https://playwright.dev/docs/emulation)
- [Playwright visual comparisons](https://playwright.dev/docs/test-snapshots)
- [W3C Media Queries Level 5](https://www.w3.org/TR/mediaqueries-5/)
