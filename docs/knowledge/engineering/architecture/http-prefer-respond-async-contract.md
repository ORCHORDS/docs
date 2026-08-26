# HTTP Prefer respond-async contract

**Issue:** A client sends `Prefer: respond-async` or `wait` and assumes the server must honor it, producing timeout, polling, and cache behavior that is not actually in the API contract.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Treat preferences as optional requests; define the normal response when each preference is ignored.
- Return `Preference-Applied` only for preferences actually honored.
- When asynchronous handling is selected, return `202 Accepted` with a stable status resource and define polling, cancellation, expiry, and final-result semantics.
- Interpret `wait` as a client preference, not a transport timeout or service-level guarantee.
- If a preference changes a cacheable representation, include `Prefer` in `Vary` or make the response uncacheable.
- Parse repeated preference tokens deterministically; RFC 7240 says only the first occurrence of a duplicated preference is considered.

## Verification

Test honored, ignored, duplicated, malformed, and intermediary-applied preferences. Verify retry and polling remain idempotent and that cached responses do not cross preference variants.

## Gotchas

A `202` response does not define how a final result is discovered. The `Prefer` field is not content negotiation and must not be treated as `Expect`.

## Official sources

- [RFC 7240: Prefer Header for HTTP](https://www.rfc-editor.org/info/rfc7240/)
