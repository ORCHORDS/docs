# Web Share Target ingress validation

**Issue:** An installed web app accepts browser share-target launches as trusted internal navigation. Crafted text, URLs, files, or repeated POSTs can then trigger side effects, exhaust storage, or cross tenant boundaries.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** experimental — feature-detect

## Registration boundary

The Web Share Target specification defines a manifest `share_target` member with an action, method, encoding, and parameter mapping. A supporting user agent turns a share into a navigation/request to that action. This is an operating-system/browser ingress, not an authenticated RPC channel.

Use a dedicated same-application endpoint and map only declared fields. Prefer POST with `multipart/form-data` when receiving files. A GET target places shared values in a URL, so it is suitable only for bounded, non-sensitive draft input and must not perform state-changing work.

## Intake controls

1. Authenticate the current app session and resolve tenant/account independently of shared parameters. Never accept a tenant, owner, or authorization role from the share payload.
2. Apply ordinary CSRF/origin/session protections appropriate to the endpoint. Installation or invocation by a browser is not proof of intent for a server-side mutation.
3. Parse using the declared encoding. Reject unexpected fields, duplicate ambiguity, malformed media types, filename path components, and values over explicit byte/count limits.
4. For files, stream to quarantine; enforce total/file limits; inspect actual content rather than trusting extension or declared MIME type; and store under generated identifiers outside executable paths.
5. Normalize URLs through the URL parser and display them for review. Do not fetch, redirect to, or render remote content automatically.
6. Stage the result as a draft. Require a visible confirmation before sending, publishing, uploading, or sharing it onward.
7. Attach an idempotency key to confirmed side effects. Browsers, service workers, and users can retry a launch.
8. Handle logged-out and expired-session launches without losing bounded draft input or leaking it into a URL/log.

## Service-worker and UI handling

Do not let the service worker blindly cache a POST body or return a generic offline success. If offline intake is supported, encrypt and bound local staging, identify its account scope, and make replay explicit.

Render all shared text as text. Object URLs for previews must be revoked. Ensure the confirmation screen works on narrow mobile viewports, keyboard-only desktop use, and installed-window navigation.

## Verification

Send empty values, oversized text, many files, zero-byte files, spoofed MIME types, duplicate fields, traversal filenames, cross-tenant parameters, unauthenticated sessions, offline launches, double submissions, and unsupported browsers. Assert no permanent side effect occurs before confirmation and every confirmed operation is idempotent.

## Gotchas

- Manifest parameter names are mappings, not validation schemas.
- A share target is a receive surface; Web Share is the separate send API.
- GET values can enter history, logs, analytics, and referrers.
- User-agent support and installation behavior vary; preserve a conventional upload/paste path.

## Sources

- [W3C Web Share Target API](https://w3c.github.io/web-share-target/)
