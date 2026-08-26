# Adaptive shell resize preserves user state

**Issue:** Crossing a viewport breakpoint remounts the application shell, resets a draft, closes the current detail, or creates a second history entry even though the user did not navigate.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Lesson

A viewport change is a layout event, not a navigation event. Preserve route, task progress, focus intent, scroll context, selection, and unsaved input while replacing only the navigation chrome or pane arrangement.

**Sources:** [W3C Media Queries Level 5](https://www.w3.org/TR/mediaqueries-5/) · [WCAG 2.2 reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html) · [WHATWG session history](https://html.spec.whatwg.org/multipage/nav-history-apis.html#the-session-history-of-browsing-contexts)

## Apply

- keep route and domain state above breakpoint-specific presentation;
- use one stable key/identity for content that moves between panes;
- model compact detail and wide list-detail as the same selection;
- preserve drafts outside disposable shell components;
- move focus only when the currently focused control ceases to exist, then choose a logical equivalent;
- do not push or replace history solely because a media query changed;
- respond to live resizing, orientation, split-screen, and zoom.

## Verify

Resize repeatedly during editing, loading, validation, modal/disclosure use, media playback, and list-detail navigation. Test browser zoom/reflow, orientation, split screen, keyboard focus, back/forward, and scroll restoration. Assert no duplicate request or mutation is triggered by remount.

## Gotchas

CSS visibility can preserve hidden focusable controls unintentionally. Component remounts often reset uncontrolled form fields. Restoring exact pixels is less useful than restoring the user's semantic position and focused task.
