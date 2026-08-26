# HTTP/2 ORIGIN frame and coalescing policy

**Issue:** A client guesses which origins an HTTP/2 connection can serve from certificate coverage alone, causing avoidable connections or misdirected requests behind multi-tenant infrastructure.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented; extension deployment varies

RFC 8336 defines the HTTP/2 ORIGIN frame so a server can indicate origins the connection is authoritative for. Treat it as an additional connection-reuse signal; normal TLS certificate, DNS, authority, and privacy rules still apply.

**Source:** [RFC 8336: ORIGIN HTTP/2 Frame](https://www.rfc-editor.org/rfc/rfc8336)

## Controls

- accept ORIGIN only on the connection where received;
- validate each advertised origin and retain certificate/security checks;
- scope cache and credentials by origin even when transport is shared;
- expire mappings when the connection closes or routing changes;
- fall back safely when endpoints/intermediaries ignore the extension.

## Verification

Test empty/multiple origins, malformed frames, SAN mismatch, proxy/CDN routing, connection migration/closure, credential isolation, 421 recovery, and servers without ORIGIN. Measure connection count and handshake savings without weakening origin boundaries.

## Gotchas

ORIGIN does not authorize cross-origin DOM access, merge HTTP caches, or override certificates. It is HTTP/2-specific. Intermediaries and deployments may not expose it consistently.
