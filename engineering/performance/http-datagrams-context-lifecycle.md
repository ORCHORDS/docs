# HTTP Datagram context lifecycle

**Issue:** An application treats HTTP Datagrams like a reliable byte stream, losing messages silently or accepting datagrams after their associated request context ended.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** protocol support and application mappings vary

RFC 9297 defines unreliable datagrams associated with HTTP request streams using context identifiers. Use them only for application data that tolerates loss, duplication, and reordering, with explicit size and lifetime policy.

**Source:** [RFC 9297: HTTP Datagrams and the Capsule Protocol](https://www.rfc-editor.org/rfc/rfc9297)

## Controls

- negotiate the application mapping and datagram capability;
- bind each context ID to one authorized request/session;
- cap payload, rate, contexts, and buffered processing;
- discard unknown or closed contexts;
- put reliable control/state transitions on a reliable channel;
- design congestion and backpressure behavior.

## Verification

Inject loss, duplication, reordering, delay, MTU pressure, context reuse, unknown IDs, request closure, migration, and fallback transport. Confirm missing datagrams cannot corrupt durable state.

## Gotchas

Unreliable does not mean uncongested or unordered by definition, only that delivery is not guaranteed. Context identifiers are not global identities. Capsule fallback has different framing/transport cost.
