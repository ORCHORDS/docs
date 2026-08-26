# http2-rapid-reset-continuation-flood

**Issue:** HTTP/2 and HTTP/3 multiplexing lets a client run many concurrent streams over one connection, and the protocol's flexibility creates asymmetric-cost attack surface at the connection layer. The HTTP/2 Rapid Reset attack (CVE-2023-44487, disclosed October 2023 and exploited at a record-breaking ~398 million requests-per-second) works by opening streams and immediately sending RST_STREAM: the client pays almost nothing while the server repeatedly starts expensive request handling before tearing it down. Months later, the HTTP/2 CONTINUATION flood (CVE-2024-27316) showed a second pattern: HEADERS frames without END_HEADERS followed by endless CONTINUATION frames hold per-stream header memory in limbo, exhausting servers from a single TCP connection. These are protocol-abuse denial-of-service attacks that no application firewall rule on URLs stops — mitigation lives in server and library configuration, concurrency caps, and edge filtering. Every service exposing HTTP/2 (which includes anything behind a modern CDN or ALPN-enabled load balancer) needs this hardening, and it must be continuously re-checked because the class keeps producing new variants.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Rapid Reset Mechanics (CVE-2023-44487)

1. **The asymmetric loop.** The client sends HEADERS for a new stream, then immediately RST_STREAM to cancel it. Servers begin request dispatch (routing, header parsing, sometimes application kickoff) on HEADERS arrival, so each cycle costs the server real CPU while the client spends a couple of small frames.
2. **Concurrency limits do not stop it.** The attack respects SETTINGS_MAX_CONCURRENT_STREAMS because canceled streams free slots instantly; the abuse is the create-cancel churn rate, not standing stream count.
3. **Amplification across layers.** Proxies that multiplex many client connections upstream can multiply the effect: modest client-side reset rates become heavy origin-side request storms, which is why CDNs patched their edges and origins simultaneously during the 2023 disclosures.
4. **HTTP/3 inherits the pattern.** QUIC stream cancellation enables an equivalent reset-based flood, so mitigations must cover h3 in addition to h2 wherever both are negotiated.

## CONTINUATION Flood (CVE-2024-27316)

1. **Unbounded header assembly.** An HTTP/2 request header set is assembled across HEADERS plus CONTINUATION frames until END_HEADERS arrives; there was historically no overall limit on how many CONTINUATION frames a single request could carry.
2. **Memory pinned with no timeout.** Each incomplete header block pins its accumulated HPACK-decoded bytes and stream state; one connection can pin server memory indefinitely, and many affected libraries never freed it until the stream errored.
3. **Single-connection efficiency.** Because the stream never technically starts, concurrency and rate limits keyed on requests-per-stream saw almost nothing — the attack hides below the thresholds most deployments had configured.
4. **Wide library blast radius.** nghttp2-based stacks, Go net/http before 1.22.2/1.21.10, Apache httpd before 2.4.59, Envoy, grpc implementations, and curl all shipped fixes in 2024; anything still pinned to pre-fix versions remains exploitable.

## Server and Library Hardening

1. **Patch the protocol stacks first.** The primary mitigation for both CVEs is running fixed versions of the HTTP/2 library and server (nghttp2, Go, Apache, Envoy, nginx — all shipped updates); configuration cannot fully compensate for a vulnerable parser, so this is a dependency-management obligation with a SLA.
2. **Cap stream creation and reset rates.** Configure server-level limits on new streams per second per connection and reject connections that exceed them; nginx and Envoy both expose post-patch knobs for RST_STREAM and stream-churn policing.
3. **Bound header budgets absolutely.** Set a total header size cap (Envoy max_request_headers_kb and equivalents), a maximum CONTINUATION-frame count per request, and a header-assembly timeout, so an incomplete header block cannot pin memory forever.
4. **Lower SETTINGS_MAX_CONCURRENT_STREAMS.** Publish a realistic ceiling (tens, not hundreds) per connection and enforce it; combined with churn limits this removes the headroom both attacks need.
5. **Connection-level circuit breakers.** Enable CPU-per-connection and memory-per-connection safeguards in the proxy tier so a single abusive connection is torn down before it degrades neighbors.

## Edge and CDN Controls

1. **Terminate HTTP/2 at a hardened edge.** Let the CDN or load balancer absorb h2/h3 from clients and speak pinned, patched HTTP to origin, so origin protocol stacks face a trusted, normalized peer rather than raw attacker-driven streams.
2. **WAF and L7 DDoS rules keyed on protocol anomalies.** Alert and challenge on per-connection RST rates, CONTINUATION volume, and header-block durations — these signals exist at the edge even when request payloads look benign.
3. **Aggressive timeouts on idle and half-open streams.** Short stream-idle and header-assembly timeouts at the edge convert pinned-memory attacks into cheap resets.
4. **Have an HTTP/1.1 fallback plan.** During a novel h2 incident, the documented emergency procedure of disabling HTTP/2 negotiation (serving HTTP/1.1) buys mitigation at a throughput cost; test that this toggle actually works before an incident.

## Operational Readiness

1. **Inventory protocol exposure.** Know which endpoints negotiate h2/h3, which library versions back them, and which are internet-facing; this map is what turns a new CVE advisory into a same-day patch sweep rather than an audit project.
2. **Load-test the cancellation path.** Include stream-create-cancel storms and CONTINUATION dribbles in resilience testing; measure CPU and memory per abusive connection and verify circuit breakers trip before user-facing degradation.
3. **Monitor protocol-frame metrics.** Export counters for RST_STREAM rate, CONTINUATION frames, rejected streams, and connection kills; both 2023-2024 attacks are visible in these counters minutes before saturation.
4. **Track the class, not just the CVEs.** CISA's rapid-reset advisory and the follow-on CONTINUATION research show a recurring pattern — protocol features that let clients create cheap-but-costly server work. Review every new protocol or transport feature (extended CONNECT, WebTransport, h3 datagrams) against that template before enabling it.
