# RFC 9298 CONNECT-UDP Tunnel Context Contract

**Issue:** UDP proxying over HTTP combines URI-template targets, Extended CONNECT, Capsules, and datagram context identifiers. Treating it like an opaque TCP tunnel breaks routing and authorization.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Validate target_host and target_port after URI-template expansion and apply destination policy before opening UDP.
- Negotiate connect-udp and the required HTTP datagram/Extended CONNECT capabilities.
- Reserve context ID zero for UDP payloads and scope nonzero context allocation to one request.
- Apply per-tunnel quotas, idle expiry, and destination-aware abuse controls.

## Verification

- Try malformed templates, private destinations, unsupported negotiation, and context collisions.
- Run over supported HTTP versions and intermediaries.
- Verify closing one request cannot affect equal context IDs in another.

## Gotchas

- The proxy can observe destinations and traffic metadata.
- CONNECT authorization must not become a generic UDP relay.

## Official sources

- https://www.rfc-editor.org/rfc/rfc9298.html
