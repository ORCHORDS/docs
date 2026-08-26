# RFC 8441 WebSocket over HTTP/2 Extended CONNECT

**Issue:** HTTP/1.1 Upgrade headers and status 101 do not apply to HTTP/2. WebSocket bootstrapping requires explicit Extended CONNECT negotiation.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Wait for SETTINGS_ENABLE_CONNECT_PROTOCOL before sending Extended CONNECT.
- Use CONNECT with :protocol websocket and correct scheme, authority, and path pseudo-headers.
- Do not send HTTP/1.1 Connection or Upgrade headers on HTTP/2.
- Preserve origin, authentication, flow-control, and cancellation policy per stream.

## Verification

- Connect with the setting enabled, absent, invalid, and reordered.
- Pass through every HTTP/2 proxy/load balancer.
- Mix WebSocket and normal streams on one connection.

## Gotchas

- Support at endpoints does not prove intermediary support.
- A WebSocket stream still needs application authorization.

## Official sources

- https://www.rfc-editor.org/rfc/rfc8441.html
