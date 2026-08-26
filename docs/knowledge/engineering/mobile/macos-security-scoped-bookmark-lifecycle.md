# macOS security-scoped bookmark lifecycle

**Issue:** A sandboxed macOS app stores a user-selected path and assumes it remains authorized after relaunch. Access then fails after restart, move, rename, or bookmark staleness; another implementation starts security-scoped access repeatedly and never balances it, leaking process-scoped access resources.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Problem and applicability

The macOS App Sandbox restricts filesystem access. A user can grant access through an open/save panel, and a security-scoped bookmark can preserve that grant for later use when the app has the appropriate entitlement and follows the bookmark lifecycle.

Use a bookmark only for a file or directory the user deliberately selected and the product genuinely needs later. Prefer a read-only entitlement and scope when mutation is not required.

## Controls and implementation

1. Obtain the URL from an Apple-provided user-selection flow. Do not manufacture a bookmark for an arbitrary path and assume it creates authority.
2. Create bookmark data with the security-scope option while the initial access is valid, then store the opaque bookmark data in app-controlled storage. Do not treat the path as the durable identity or authorization.
3. On each use, resolve the bookmark with security scope enabled and inspect the stale result. If stale, recreate and atomically replace the stored bookmark while valid access is active.
4. Call startAccessingSecurityScopedResource on the resolved URL and check its Boolean result. Perform only the bounded operation that needs access.
5. Balance every successful start with stopAccessingSecurityScopedResource using a defer/finally-style structure, including error and cancellation paths. Do not hold access for the entire app lifetime merely for convenience.
6. Re-prompt through a clear user flow when resolution or access fails. Never silently widen access or loop on permission prompts.
7. Store display metadata separately from the bookmark and refresh it after resolution. A moved or renamed file can remain the same selected resource even when its path changes.
8. Apply least-privilege sandbox entitlements, code signing, and container ownership consistently across release and helper targets. Do not log bookmark bytes or unrelated user paths.

## Verification

Test first selection, app relaunch, file and parent-folder move/rename, stale-bookmark refresh, deletion, revoked access, read-only versus read-write behavior, repeated concurrent access, cancellation, helper process use, app update, code-sign identity change, and corrupted stored data.

Instrument successful starts and balanced stops in debug builds. Confirm access is unavailable before resolution, remains limited to the selected scope, and fails with a recoverable UI when the resource no longer exists.

## Gotchas

- A bookmark is an opaque persistent reference, not a secret capability to copy between arbitrary apps.
- A raw path can be valid while sandbox authorization is absent.
- Starting access consumes process resources; unmatched starts are a lifecycle bug.
- Entitlement and bookmark behavior differ between document access and broader user-selected directories.

## Official sources

- [Apple — Accessing files from the macOS App Sandbox](https://developer.apple.com/documentation/security/accessing-files-from-the-macos-app-sandbox)
- [Apple — Bookmark creation options](https://developer.apple.com/documentation/foundation/url/bookmarkcreationoptions)
