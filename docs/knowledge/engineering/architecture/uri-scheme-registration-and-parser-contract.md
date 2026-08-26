# URI scheme registration and parser contract

**Issue:** RFC 7595 governs URI scheme registration. Minting an unregistered private scheme or treating an unknown scheme as an HTTP URL creates collision, dispatch, and security ambiguity.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Prefer existing schemes; document syntax, semantics, normalization, security, internationalization, and identifier persistence; centralize dispatch and deny unknown privileged handlers.

## Verification

Round-trip valid forms; reject control characters and ambiguous encodings; test OS/browser handler conflicts, Unicode, relative-reference assumptions, and unknown schemes.

## Gotchas

A scheme name does not confer trust. Generic URI parsers may accept syntax that the scheme-specific contract forbids, and provisional registration is not permanent status.

## Official sources

- https://www.rfc-editor.org/rfc/rfc7595
