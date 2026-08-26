# Adaptive shells preserve route and task semantics

**Issue:** Compact and wide layouts implement the same destination as different application states, so links, history, focus, and deep links behave differently when only the navigation chrome changed.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Lesson

An adaptive shell may change how navigation is presented, but it must not change what a destination means. Keep one canonical route and task model; render that model through bottom tabs, a rail, a sidebar, or another shell appropriate to available space.

**Sources:** [WHATWG HTML links](https://html.spec.whatwg.org/multipage/links.html) · [WHATWG Navigation API](https://html.spec.whatwg.org/multipage/nav-history-apis.html#navigation-api) · [WCAG 2.2 consistent navigation](https://www.w3.org/WAI/WCAG22/Understanding/consistent-navigation.html)

## Apply

- assign every primary destination one stable URL, accessible name, authorization rule, and analytics identity;
- use real links for navigation and buttons for actions in every shell;
- derive active destination from route state rather than separate chrome-local selection;
- keep browser back/forward, refresh, fragments, and deep links equivalent;
- centralize route metadata so labels and permissions cannot drift by breakpoint.

## Verify

Run the same destination contract through compact and wide shells. Test direct URL entry, keyboard navigation, history traversal, refresh, authorization failure, offline failure, and shell changes mid-route. The content landmark and route identity must remain stable.

## Gotchas

Visual placement is not route identity. Duplicating route trees for mobile and desktop creates silent semantic drift. Responsive CSS cannot repair a button incorrectly used as a link.
