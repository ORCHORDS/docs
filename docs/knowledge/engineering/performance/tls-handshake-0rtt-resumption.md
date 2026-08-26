# tls-handshake-0rtt-resumption

**Issue:** Before a browser sends a single HTTP byte it must resolve DNS, open a TCP (or QUIC) connection, and complete a TLS handshake, and on cold connections that handshake alone commonly costs 1-2 round trips, which can be 200+ ms on a transatlantic path. TTFB budgets die here. TLS 1.3 cut the full handshake to 1-RTT, and session resumption with 0-RTT early data lets a returning client send its HTTP request inside the first flight, collapsing crypto setup to effectively zero extra round trips. Meanwhile certificate chain bloat (multiple intermediates, RSA keys, and now post-quantum hybrid certificates that inflate ClientHello sizes dramatically per 2025 research) silently gives back those gains. Optimizing the TLS layer is one of the highest-leverage TTFB improvements available, and it is invisible to application profiling.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The round-trip math

1. **TLS 1.3 full handshake is 1-RTT.** Key exchange (via key_share groups like X25519) completes in one round trip, versus 2-RTT for TLS 1.2 full handshake. On a 150 ms RTT path that is a flat 150 ms saved on every cold connection.
2. **Resumption without 0-RTT is still 1-RTT.** A session ticket or PSK lets the client skip certificate validation but still waits one round trip before sending HTTP data. Good, but the request still pays the full RTT.
3. **0-RTT removes the last round trip.** With early data, the client sends the PSK binder and its HTTP request (typically the GET for the HTML document) in the first flight. The server can respond immediately, so connection setup adds near-zero latency for returning visitors. Cloudflare's production measurements of 0-RTT showed substantial TTFB improvements for resumed connections.
4. **QUIC multiplies the effect.** Over HTTP/3, 0-RTT TLS combines with 0-RTT connection establishment in QUIC, eliminating the TCP handshake too; the stack becomes TLS 1.3 + QUIC + resumption as the current best-practice latency baseline.

## Certificate chain hygiene

1. **Send the minimal chain.** Every intermediate certificate adds kilobytes that must fit in TCP initial congestion windows; an oversized chain forces extra round trips before the handshake completes. Use a chain checker to confirm exactly leaf plus the intermediates needed, no cross-signed duplicates, no root.
2. **Prefer ECDSA (P-256) leaf certificates.** ECDSA certificates are a few hundred bytes versus roughly 1-2 KB for RSA-2048, and signing is cheaper; smaller Certificate messages fit the initial flight more reliably. Keep an RSA chain only if very old client support demands it.
3. **OCSP stapling, not client-side revocation checks.** Staple the OCSP response (and ideally a full multi-stapled set) so clients do not perform revocation lookups serially; browsers otherwise silently skip or delay revocation, and either behavior costs latency or security. Must-Staple plus a short-lived certificate strategy keeps stapled responses fresh.
4. **Watch the post-quantum ClientHello.** Hybrid PQ key shares (X25519MLKEM768) inflate the ClientHello toward 2 KB and beyond; 2025 measurements (arXiv study on PQ chain sizes and TTFB) show measurable TTFB regression on lossy or narrow initial windows, and mismatched middleboxes can break connections entirely. Prefer a CDN that terminates PQ at tuned edge settings over hand-rolling it.

## Resumption mechanics to get right

1. **Session tickets need shared infrastructure.** TLS session tickets encrypt resumption state with a ticket key; behind a load balancer, every server (or every Cloudflare Worker colo / nginx instance) must share rotating ticket keys or resumption fails and silently reverts to full handshakes. Rotate keys on a schedule (for example every 24-48 h with overlap) to bound ticket replay windows.
2. **Tickets must outlive connections.** Issue tickets with a lifetime matched to realistic return-visit intervals (hours, not minutes); overly short ticket lifetimes mean most returning users pay full handshakes anyway.
3. **0-RTT has replay risk.** RFC 8446 is explicit: early data has no forward secrecy and can be replayed. Never accept non-idempotent requests (POST payments, anything mutating) as 0-RTT early data at the application layer; require the handshake to complete first, or include a single-use anti-replay nonce. This is a security requirement that directly shapes your TTFB optimization scope.

## Verification and monitoring

1. **Confirm resumption rates server-side.** Log handshake type (full vs resumed vs 0-RTT) per connection. A resumption rate near zero on a site with returning users almost always means broken ticket-key sharing or overly aggressive key rotation.
2. **Check from real clients.** In DevTools Security panel or with openssl s_client -reconnect, verify the second connection reuses the session. Chrome's net-export traces flag early-data acceptance directly.
3. **Measure TTFB split by connection state.** Segment RUM TTFB into cold (DNS + TCP + full TLS) versus warm (resumed) cohorts; the gap quantifies exactly how much the TLS layer is costing your cold-visit users, and whether 0-RTT is actually engaged.
