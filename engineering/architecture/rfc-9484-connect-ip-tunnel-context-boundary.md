# RFC 9484 CONNECT-IP tunnel context boundary

**Issue:** CONNECT-IP carries IP packets through an HTTP proxy using HTTP Datagrams and a capsule protocol. Treating it like an ordinary request tunnel can mix address contexts, bypass egress policy, or mishandle route withdrawal and datagram loss.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Authenticate and authorize each tunnel independently; bind permitted IP prefixes, address families, destinations, duration, and quota to that tunnel context.
- Validate address-assignment and route-advertisement capsules, reject overlapping or unauthorized prefixes, and withdraw forwarding state when the stream closes.
- Enforce anti-spoofing on inner source addresses and normal egress, abuse, logging, and tenant-isolation policy after decapsulation.
- Bound datagram size, reorder/loss tolerance, capsule parsing, idle time, and aggregate bandwidth without treating unreliable delivery as a reliable byte stream.

## Verification

1. Exercise IPv4/IPv6 assignment, unauthorized and overlapping routes, spoofed sources, malformed capsules, unknown capsule types, and oversized datagrams.
2. Drop, duplicate, and reorder datagrams; reset the control stream and prove forwarding state is removed.
3. Run two tenant tunnels with similar private prefixes and prove their policy, quota, and telemetry remain isolated.
4. Confirm clients and proxies without protocol support fail explicitly rather than falling back to an unrestricted tunnel.

## Gotchas

CONNECT-IP is an IP proxy, not a VPN security policy by itself. HTTP success establishes a protocol context but does not authorize arbitrary inner traffic. Datagram loss is expected, and stale routes after control-stream failure create a serious isolation defect.

## Official sources

- https://www.rfc-editor.org/rfc/rfc9484
- https://www.rfc-editor.org/rfc/rfc9297
