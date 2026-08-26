# Implement RFC 9865 SCIM Cursor Pagination as a Negotiated Contract

**Issue:** RFC 9865 adds cursor pagination to SCIM and updates RFCs 7643 and 7644. Mixing cursor and index behavior without advertised capability and stable request semantics causes interoperability failures.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Advertise supported pagination methods, default method, cursor timeout, and maximum page size in Service Provider Configuration.
- Keep cursor values opaque and URL-safe; do not ask clients to parse implementation state.
- Require subsequent requests to preserve original query parameters and count as specified.
- Return `nextCursor` on every non-final page and omit it only at the end; return `previousCursor` only when supported and never on the first page.
- Emit the RFC-defined SCIM error types for expired cursors, invalid cursors, and invalid counts.
- Preserve index pagination as the default when adding cursors to an existing index-only provider unless a deliberate compatibility migration says otherwise.

## Verification

- Contract-test first, middle, final, reverse, expired, tampered, and cross-query cursor requests.
- Confirm a page may contain fewer than `count` resources without signaling completion.
- Test cursor use across the documented timeout and across every service node.
- Run legacy index-pagination clients against the upgraded provider.

## Gotchas

`totalResults` can change while pages are traversed. Cursor opacity is not access control; authorization must be reevaluated on each request.

## Official sources

- [RFC 9865: Cursor-Based Pagination of SCIM Resources](https://www.rfc-editor.org/rfc/rfc9865.html)
