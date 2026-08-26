# Cookie Store Async Access and Change Events

**Issue:** Synchronous `document.cookie` access blocks the main thread, requires fragile string parsing, and is unavailable in service workers; session-dependent caches then drift across tabs and workers.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented
**Compatibility:** Newly available in current browsers; feature-detect for older clients.

## Control pattern

Use the promise-based Cookie Store API for script-visible cookies: `cookieStore.get()`, `getAll()`, `set()`, and `delete()`. Always set explicit path, SameSite, Secure, and expiry policy. Subscribe to `change` only to invalidate or refresh derived client state; server authorization must continue to validate the actual request cookie.

In a service worker, register narrowly scoped cookie change subscriptions and keep handlers idempotent. Provide a `document.cookie` adapter only where the API is absent. Do not attempt to expose or manipulate HttpOnly cookies: their deliberate invisibility to script is a security boundary.

## Verification

Test set/update/delete, same-name cookies on different paths, expiry, secure and insecure contexts, partitioned browsing, multiple tabs, service-worker restart, event coalescing, and unsupported browsers. Verify logout invalidates client caches but does not rely on an event to revoke server access. Measure main-thread improvement rather than assuming it.

## Gotchas

A change event may describe only script-visible cookies and is not a transactional authorization signal. Cookie scope rules still apply. Broad service-worker subscriptions increase wakeups. Compatibility varies for some event/subscription surfaces even where window methods exist.

## Sources

- [WHATWG Cookie Store API Living Standard](https://cookiestore.spec.whatwg.org/)
- [MDN Cookie Store API compatibility and usage](https://developer.mozilla.org/en-US/docs/Web/API/Cookie_Store_API)
