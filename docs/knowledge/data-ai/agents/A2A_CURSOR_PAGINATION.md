# A2A Cursor Pagination for Task Listings

## Purpose

A2A v1.0 adopts cursor-based pagination for scalable task listing. Clients should treat cursors as opaque continuation values rather than reconstructing page positions or assuming stable numeric offsets.

## Guidance

1. Preserve a returned cursor exactly and send it only to the same logical listing operation and scope.
2. Do not parse security or business meaning from opaque cursor contents.
3. Bind authorization to every page request; possession of a cursor must not grant broader access.
4. Apply a reasonable page size and total-work budget so listings cannot cause unbounded memory or latency.
5. Handle empty pages and expired or invalid cursors explicitly.
6. Expect underlying task data to change between pages and avoid assuming a cursor produces a frozen snapshot unless the server promises that property.
7. Keep tenant, filter, and caller scope consistent across continuation requests.

## Sources

- A2A Protocol — What's New in v1.0: https://a2a-protocol.org/latest/whats-new-v1/
- A2A Protocol — current specification: https://a2a-protocol.org/dev/specification/

## Scope note

Cursor pagination improves scalability and continuation semantics. Exact consistency guarantees depend on the server implementation and should be documented separately.
