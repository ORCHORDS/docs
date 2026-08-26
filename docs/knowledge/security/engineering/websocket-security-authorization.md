# websocket-security-authorization

**Issue:** WebSocket connections begin as an HTTP upgrade handshake and then become long-lived bidirectional sockets that bypass the assumptions most applications make about HTTP security. The handshake is not covered by CORS in a way developers expect, browsers attach ambient cookies to it from any origin unless the server checks, and the connection can stay open for hours while permissions change. The resulting vulnerability class, cross-site WebSocket hijacking (CWE-1385), lets an attacker's page open an authenticated socket using the victim's session cookies and then read or write through it as the victim. Beyond hijacking, common failures include authenticating only at handshake, trusting query-string tokens that leak into logs and proxies, and granting the whole connection one coarse permission level for its lifetime.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Handshake authentication

1. **Validate the Origin header against an allowlist.** Reject any handshake whose Origin is not an exact match for a trusted origin; treat a missing Origin as hostile for browser-facing services, since browsers always send it and only non-browser clients omit it.
2. **Do not rely on CORS to protect the upgrade.** The WebSocket handshake is not subject to CORS preflight or response blocking, so a cross-origin page can open the socket and receive messages that same-origin policy would have withheld from fetch; Origin checking at the server is mandatory, not optional.
3. **Prefer short-lived tokens over query strings.** Because browsers cannot set custom headers on the handshake, pass a one-time, short-TTL token in the Sec-WebSocket-Protocol field or a cookie, and exchange it during or immediately after the handshake for the real session; never place long-lived credentials in the URL, where they leak to logs, proxies, and Referer headers.
4. **Authenticate before accepting protocol upgrade.** Reject unauthorized handshakes with 401/403 before the 101 switching protocols response so unauthenticated sockets never reach application logic.
5. **Re-authenticate on reconnect.** Treat every reconnect as a fresh handshake with full token validation; reusing a connection ticket across reconnects extends stolen-token lifetime indefinitely.

## Per-message authorization

1. **Authorize every message, not just the connection.** A socket opened when the user had rights can outlive a permission revocation, demotion, or logout; re-evaluate authorization per message or per topic subscription against current state.
2. **Enforce topic and channel ACLs.** Validate that the authenticated principal may subscribe or publish to each channel identifier; never derive authorization from a client-supplied user or room field echoed back by the server.
3. **Handle revocation actively.** Maintain a connection registry keyed by user ID so logout, password change, or admin suspension can terminate or downgrade live sockets within seconds rather than waiting for the next message.
4. **Never treat authenticated transport as message integrity.** Messages inside an authenticated socket still originate from client-controlled script; include anti-replay sequencing or nonces for high-value commands so a malicious page or injected script cannot replay privileged frames.

## Transport and message hardening

1. **Require TLS and reject downgrade.** Serve WebSockets only over wss with modern TLS configuration, and reject plain ws in production; long-lived authenticated channels over plaintext expose the entire session to interception.
2. **Validate message schema strictly.** Parse each frame against a typed schema with depth and size limits, since JSON parsing of unbounded payloads invites memory exhaustion and prototype-pollution-style abuse of poorly structured handlers.
3. **Apply backpressure and rate limits per connection.** Enforce inbound frame rate, maximum message size, and queue depth per socket so one client cannot monopolize the event loop or memory; drop or close connections that exceed budgets.
4. **Authenticate the close path.** Ensure server-initiated close frames propagate cleanly so authorization state does not linger in half-open connections behind load balancers with long idle timeouts.

## Deployment and testing

1. **Protect the upgrade route at the edge.** Place the WebSocket endpoint behind the same WAF, bot management, and IP reputation controls as the HTTP API; many stacks exclude upgrade traffic from inspection by default.
2. **CSWSH regression tests.** Automated tests should attempt the handshake from a foreign Origin with ambient cookies and assert rejection, plus attempt to subscribe to another user's channels after authentication succeeds.
3. **Fuzz the frames.** Include malformed, oversized, and rapidly repeated frames in integration tests to confirm schema validation and rate limiting respond rather than crash.
4. **Monitor connection lifecycles.** Alert on anomalous connection duration, message volumes per socket, and handshakes from origins outside the allowlist to detect hijacking and abuse in progress.

## References informing this article

1. **PortSwigger Web Security Academy, Cross-site WebSocket Hijacking.** Canonical explanation of CSWSH mechanics and the Origin-validation fix.
2. **MITRE CWE-1385, Missing Origin Validation in WebSockets.** Formal weakness definition covering the handshake trust gap.
3. **Include Security and Praetorian CSWSH write-ups (2025).** Current exploitation recaps and defense checklists for production stacks.
4. **HackerOne report 535436 (Coda Docs).** Real-world bounty case showing cookie-inheriting cross-origin sockets in the wild.
