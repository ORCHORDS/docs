# Navigation API Interception, Focus, and Scroll Contract

**Issue:** A client router can update history before rendering succeeds, intercept ineligible navigation, or lose browser focus and scroll semantics.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Listen for `navigation.navigate`, but return immediately when `canIntercept` is false, for downloads, cross-origin targets, or routes the application does not own. Use `intercept()` only for same-document routing. Treat its handler signal as cancellation: abort fetch and rendering when a newer navigation supersedes it.

Prefer browser focus and scroll defaults. If `focusReset:"manual"` is necessary, focus the new page heading or main landmark after content becomes usable without stealing focus from an explicit user action. If `scroll:"manual"` is used, implement fragment navigation and history restoration, or invoke `event.scroll()` at the correct rendering milestone.

Keep ordinary links and server responses functional as fallback. Separate precommit authorization/redirect decisions from postcommit rendering, and expose navigation failures without leaving a permanent loading state.

## Verification

Test link, POST form, programmatic, reload, traverse, fragment, download, cross-origin, redirect, rapid double navigation, cancellation, render rejection, and offline failure. Verify URL/history entries, back/forward behavior, focus announcement, scroll restoration, analytics count, and no stale response overwrites newer content. Run tests without Navigation API support.

## Gotchas

The URL can commit before an async handler finishes. Manual focus/scroll disables useful browser behavior and transfers the full accessibility obligation to the app. Interception is routing, not an authorization boundary; the server must enforce access.

## Sources

- [MDN Navigation API](https://developer.mozilla.org/en-US/docs/Web/API/Navigation_API)
- [MDN NavigateEvent.intercept](https://developer.mozilla.org/en-US/docs/Web/API/NavigateEvent/intercept)
- [WHATWG HTML Navigation API](https://html.spec.whatwg.org/multipage/nav-history-apis.html#navigation-api)
