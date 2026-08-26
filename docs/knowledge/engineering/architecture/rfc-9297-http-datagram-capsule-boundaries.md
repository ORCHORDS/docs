# Preserve RFC 9297 HTTP Datagram and Capsule Boundaries

**Issue:** HTTP Datagrams may use unreliable QUIC DATAGRAM delivery or reliable Capsule transport. Conflating them breaks loss, ordering, size, and flow-control assumptions.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Use HTTP Datagrams only through an extension that defines their payload semantics.
- Negotiate HTTP/3 datagrams with the specified setting before sending them.
- Associate datagrams with an open request stream and enforce extension-specific size limits.
- Ignore unknown capsule types and bound buffering before reading declared lengths.
- Preserve intended unreliability when an intermediary re-encodes transport forms.

## Verification
- Test loss, reorder, duplication, stream closure, unknown capsule types, and malformed variable integers.
- Cross an intermediary that converts QUIC DATAGRAM frames and DATAGRAM capsules.
- Exercise PMTU reduction and oversized capsule declarations.

## Gotchas
Capsules are reliably ordered on a stream; QUIC DATAGRAM frames are not. RFC 9297 is an extension substrate, not an application datagram API.

## Official sources
- [RFC 9297](https://www.rfc-editor.org/rfc/rfc9297.html)
