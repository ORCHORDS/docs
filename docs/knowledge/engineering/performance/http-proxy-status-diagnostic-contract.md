# HTTP Proxy-Status diagnostic contract

**Issue:** A request is slow or fails through several intermediaries, but applications collapse every proxy, DNS, connection, and upstream failure into one generic gateway error.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

RFC 9209 defines the `Proxy-Status` response field for intermediaries to report structured handling information. Use allowlisted parameters for diagnosis while preventing internal topology and sensitive detail leakage.

**Source:** [RFC 9209: The Proxy-Status HTTP Response Header Field](https://www.rfc-editor.org/rfc/rfc9209)

## Controls

- append entries in intermediary order without overwriting prior trusted information;
- expose only registered/approved error types and bounded details;
- strip or rewrite untrusted inbound fields at the trust boundary;
- avoid hostnames, addresses, tenant IDs, and raw exception text;
- correlate with trace IDs separately and enforce header-size limits.

## Verification

Test DNS, connection, timeout, TLS, upstream, proxy-generated response, multiple hops, malformed/oversized input, and cache paths. Confirm external responses disclose only reviewed information.

## Gotchas

Proxy-Status is diagnostic, not proof of root cause or authorization. Clients can send forged fields. Detailed proxy identity can expose infrastructure and must be policy-controlled.
