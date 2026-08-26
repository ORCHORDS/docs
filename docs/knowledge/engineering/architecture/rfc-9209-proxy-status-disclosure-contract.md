# Govern RFC 9209 Proxy-Status Across Intermediaries

**Issue:** Generic 502 and 504 responses hide which intermediary failed, but unrestricted Proxy-Status parameters can disclose internal topology and untrusted claims.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Define which trusted intermediaries append entries and preserve origin-to-client ordering.
- Emit registered, specific error types and align generated HTTP status where feasible.
- Redact next-hop and details for public clients; expose richer diagnostics only through an authorized path.
- Parse the field as Structured Fields and ignore unknown parameters as required.
- Treat Proxy-Status as diagnostic input, never authenticated proof.

## Verification
- Inject DNS, connect, TLS, protocol, and response timeouts at each hop.
- Test multi-hop order, malformed fields, unknown parameters, and trailers.
- Scan public responses for internal hostnames and addresses.

## Gotchas
Origin servers must not generate Proxy-Status. Trailers may be discarded, and a proxy can make inaccurate claims.

## Official sources
- [RFC 9209](https://www.rfc-editor.org/rfc/rfc9209.html)
