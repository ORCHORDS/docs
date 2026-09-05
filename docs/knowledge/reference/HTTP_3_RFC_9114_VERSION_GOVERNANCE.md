---
title: HTTP/3 Version Governance (RFC 9114, RFC 9204, RFC 9298, RFC 9220)
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: IETF RFC 9114 (June 2022); RFC 9204 (June 2022); RFC 9298 (August 2022); RFC 9220 (June 2022); https://www.rfc-editor.org/rfc/rfc9114
---

# HTTP/3 Version Governance (RFC 9114, RFC 9204, RFC 9298, RFC 9220)

## Scope

This card governs how `orchords-docs` evaluates, deploys, and operates HTTP/3 endpoints. It is the reference input for the API gateway, edge load balancer, and any reverse-proxy or origin-server configuration committed to `orchords-docs` infrastructure.

## Why this card exists

HTTP/3 is the first major HTTP version that does not run over TCP. The protocol stack change (HTTP semantics over QUIC over UDP) shifts the failure model, congestion control, and connection-migration semantics, and shifts the operational observability story (no more TCP retransmit counters). A KB card that calls out "HTTP/3" without binding to the underlying QUIC version (RFC 9000) and QPACK (RFC 9204) produces a configuration that the operator cannot debug.

## Protocol version support matrix

| Spec | Status | Implemented in |
|---|---|---|
| RFC 9000 — QUIC v1 | IETF Standard (May 2021) | nginx 1.25+, Envoy 1.19+, HAProxy 2.6+, Cloudflare, LiteSpeed |
| RFC 9114 — HTTP/3 | IETF Standard (June 2022) | same set as QUIC v1 |
| RFC 9204 — QPACK | IETF Standard (June 2022) | same set as QUIC v1 |
| RFC 9220 — Bootstrapping WebSockets over HTTP/3 | IETF Standard (June 2022) | nginx 1.25+, Envoy 1.22+, Cloudflare Workers |
| RFC 9298 — Proxying HTTP/3 | IETF Standard (August 2022) | Envoy 1.24+, nginx 1.25+ (partial) |
| RFC 9369 — QUIC v2 | IETF Standard (May 2023) | nginx 1.25+ (experimental), Cloudflare, LiteSpeed |
| RFC 9412 — QUIC version-independent invariants | IETF (informational, 2023) | n/a (design document) |

References: `https://www.rfc-editor.org/rfc/rfc9114`, `https://www.rfc-editor.org/rfc/rfc9204`, `https://www.rfc-editor.org/rfc/rfc9220`, `https://www.rfc-editor.org/rfc/rfc9298`, `https://www.rfc-editor.org/rfc/rfc9369`.

## Stream / frame / connection surface

The HTTP/3 framing runs over QUIC streams. Every reference card that touches HTTP/3 must know:

- **Connection**: QUIC connection; QUIC v1 and QUIC v2 are not interoperable without version negotiation.
- **Streams**: unidirectional (control, QPACK encoder/decoder) and bidirectional (request/response). HTTP/3 request = bidirectional stream.
- **Frames**: HEADERS, DATA, SETTINGS, PUSH_PROMISE (server push, deprecated in practice), GOAWAY, MAX_PUSH_ID, PRIORITY_UPDATE (RFC 9218), CANCEL_PUSH.
- **QPACK**: static table (RFC 9204 § A.1), dynamic table, encoder/decoder streams. Compressed headers (h3-29, h3-30) are obsolete.

## Transport version policy

- **QUIC v1 (RFC 9000)**: required baseline. Every HTTP/3 endpoint must be capable of negotiating v1.
- **QUIC v2 (RFC 9369)**: opt-in. Enable only when both endpoints (CDN, origin) confirm v2 capability; fall back to v1 on negotiation failure.
- **Version negotiation**: `Alt-Svc: h3=":443"; ma=2592000` for advertising HTTP/3 over HTTP/1.1 or HTTP/2 fallback.

## Alt-Svc advertisement and version pinning

The KB reference architecture prescribes:

| Mode | Alt-Svc header | `h3` token | TTL |
|---|---|---|---|
| Browser-facing | required | `:443` | 30 days (`ma=2592000`) |
| API gateway (machine-to-machine) | optional | `:443` | 24 hours |
| Backend-only | not advertised | n/a | n/a |

## Congestion control

QUIC ships a CC algorithm called **QUIC loss recovery + CUBIC / BBR**. The reference card for any HTTP/3 endpoint must specify:

- The CC algorithm (CUBIC is the safe default; BBR v3 is preferred when both endpoints support it).
- Initial congestion window (RFC 6928 minimum 10 MSS, current guidance 30 MSS).
- ECN (Explicit Congestion Notification) — RFC 9000 § 19.3.2 mandates ECN support.

## Connection migration

QUIC supports connection migration via the `connection_id`. Policy:

- **NAT rebind tolerance**: support connection migration on `disrupted_path` for up to 30 seconds without dropping the request stream.
- **Path validation**: use `PATH_CHALLENGE` / `PATH_RESPONSE` before resuming streams on a new path.
- **Mobile clients**: clients may roam between Wi-Fi and cellular; the reference must enable path validation.

## 0-RTT and replay

RFC 9001 governs 0-RTT data. Policy:

- 0-RTT is allowed **only** for idempotent requests (`GET`, `HEAD`, `OPTIONS`).
- 0-RTT is forbidden for any request that changes server state.
- Anti-replay window: 0-RTT data must be tagged with the client's clock skew bound; the server rejects replayed 0-RTT outside the window.
- `Early-Data` response header carries `1` for 0-RTT accepted; the server must emit `425 Too Early` for any replayed non-idempotent 0-RTT.

## TLS 1.3 in QUIC

QUIC integrates TLS 1.3 (RFC 8446) on a separate "TLS" stream within the QUIC connection.

- TLS 1.3 only — TLS 1.2 is forbidden inside QUIC.
- Cipher suites: TLS_AES_256_GCM_SHA384, TLS_AES_128_GCM_SHA256, TLS_CHACHA20_POLY1305_SHA256. The first two are required baseline.
- Key share: X25519 (preferred), P-256, P-384. ECDHE only; never ECDH-static.

## Mandatory pre-flight (before enabling HTTP/3 on a public endpoint)

1. Confirm UDP/443 is not blocked by any upstream firewall or carrier.
2. Confirm the origin supports HTTP/3 with QUIC v1.
3. Validate Alt-Svc advertisement on HTTP/1.1 and HTTP/2 fallback paths.
4. Validate 0-RTT rejection for non-idempotent methods.
5. Validate connection migration under simulated NAT rebind.
6. Validate ECN reporting and packet marking in a staging test.

## Observability

HTTP/3 introduces a new family of metrics that map onto, but do not replace, TCP metrics:

- `quic.connection.count` (gauge, broken by version)
- `quic.handshake.latency_ms` (histogram)
- `quic.stream.bytes_sent` / `bytes_received`
- `quic.connection.migration.count`
- `quic.zero_rtt.accepted.count` / `quic.zero_rtt.rejected.count`
- `qpack.blocked_streams` (must be ≤ 1 in steady state)

## Sources

- RFC 9000 (QUIC v1): `https://www.rfc-editor.org/rfc/rfc9000`
- RFC 9114 (HTTP/3): `https://www.rfc-editor.org/rfc/rfc9114`
- RFC 9204 (QPACK): `https://www.rfc-editor.org/rfc/rfc9204`
- RFC 9220 (Bootstrapping WebSockets): `https://www.rfc-editor.org/rfc/rfc9220`
- RFC 9298 (Proxying HTTP/3): `https://www.rfc-editor.org/rfc/rfc9298`
- RFC 9001 (TLS over QUIC): `https://www.rfc-editor.org/rfc/rfc9001`
- RFC 9369 (QUIC v2): `https://www.rfc-editor.org/rfc/rfc9369`
