# HTTP 421 connection-coalescing retry boundary

**Issue:** An HTTP/2 or HTTP/3 client coalesces origins onto one connection and receives 421, then retries blindly or loops on the same unsuitable connection.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

HTTP 421 Misdirected Request means the origin cannot produce a response for the connection context. A client may retry on a different connection, but replay safety and retry bounds still apply.

**Source:** [RFC 9110 — 421 Misdirected Request](https://www.rfc-editor.org/rfc/rfc9110#name-421-misdirected-request)

## Controls

- remove the unsuitable connection/origin association before retry;
- retry automatically only when request semantics/body are replayable;
- cap retries and surface repeated 421s;
- keep authority, SNI, certificate validation, proxy, and Alt-Svc state aligned;
- partition authenticated/privacy-sensitive traffic appropriately.

## Verification

Test coalesced origins, different certificates/SNI, reverse-proxy routing errors, streaming bodies, unsafe methods, proxy paths, repeated 421, H2 and H3. Confirm a retry opens/selects a suitable connection and happens at most once by policy.

## Gotchas

421 is not a generic origin overload response. Retrying on the same connection can loop. Connection coalescing eligibility does not guarantee every intermediary routes all authorities correctly.
