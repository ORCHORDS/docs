# OTLP HTTP Versus gRPC Export Selection

OTLP defines two transports: OTLP/gRPC over HTTP/2 with protobuf payloads, and OTLP/HTTP, a plain REST-style protocol carrying protobuf (optionally JSON) over POST requests. Both are standards-track specs with default ports (4317 for gRPC, 4318 for HTTP), and both support the same telemetry signals. The choice is therefore rarely about capability and mostly about environment: what lives between the SDK and the collector, what load balancing exists, and how retries and partial failures should behave.

## Scope

Covers the selection between OTLP/gRPC and OTLP/HTTP for SDK-to-collector and collector-to-backend export: protocol mechanics, proxy and firewall traversal, load-balancer behavior (L4 versus L7), retry and throttle semantics, payload encoding options, and operational security considerations. Applies to OpenTelemetry SDKs and the Collector's OTLP receiver/exporter pair. Excludes vendor-specific exporters and the internal architecture of gateway tiers.

## Workflow or implementation guidance

Decide by walking the network path, then the failure semantics.

1. Map the path between producer and consumer. If anything in between is an HTTP/1.1-only proxy, a TLS-terminating L7 load balancer with body inspection, or a service mesh sidecar with HTTP semantics, OTLP/HTTP traverses it natively — it is ordinary POST traffic with content negotiation. gRPC requires HTTP/2 end to end; intermediaries that downgrade or buffer HTTP/2 frames break it, forcing grpc-gateway workarounds. In restrictive enterprises and embedded networks, HTTP's blandness is the decisive advantage.
2. Consider load balancing. gRPC's long-lived HTTP/2 streams pin a client to one backend connection, so naive L4 balancers send all of one client's traffic to one collector, skewing distribution; you need either an L7 balancer aware of HTTP/2, client-side load balancing, or a gateway tier that accepts streams and redistributes. OTLP/HTTP requests are independent, so every round-robin or least-connections balancer distributes them without special support.
3. Evaluate retry and throttle behavior you want to inherit. The gRPC transport exposes gRPC codes: retryable codes, server-side throttling signaled via specific codes, and the Collector's exporterhelper honoring RetryInfo delays. OTLP/HTTP uses plain status codes: 429 for throttling with Retry-After, 5xx retryable, 4xx fatal. Both are specified; which is easier to operate depends on your tooling — HTTP codes are observable in any access log, while gRPC codes require protocol-aware logging.
4. Choose the payload encoding (HTTP only). OTLP/HTTP accepts protobuf (the efficient default) and JSON (the debuggable option). JSON is invaluable during bring-up — you can read payloads with curl and inspect exactly what an SDK emits — and a liability at volume; standardize on protobuf with JSON as a documented debugging escape hatch.
5. Decide compression uniformly. Both transports support gzip; enabling it trades CPU on both ends for network bytes. Decide per link based on where the constraint is: cross-zone or internet paths usually want compression, same-host agent-to-collector links often do not.
6. Pin the decision per hop in configuration with a rationale comment. A common pattern is HTTP for the SDK-to-gateway hop (proxy-friendly, JSON-debuggable at the edge) and either transport for the gateway-to-backend hop on a private network where HTTP/2 is guaranteed.

Whatever the choice, both endpoints must agree on signal paths: OTLP/HTTP uses per-signal endpoints (`/v1/traces`, `/v1/metrics`, `/v1/logs`), while gRPC uses one endpoint with signal-specific RPC methods. Misconfigured endpoint paths produce 404s that look like connection failures if you are not reading status codes carefully.

## Controls

- Transport and encoding decision recorded per hop in the pipeline's configuration comments, with the network constraint that drove it.
- Compression setting pinned per link with a measured bytes-versus-CPU comparison filed at setup.
- Retry configuration on the exporter (backoff and elapsed budget) aligned with the consumer's expected transient-failure window, for either transport.
- Health checking on the receiver (the Collector's health check extension) verified for the chosen transport so balancers remove wedged collectors.
- Access-log or gRPC-code monitoring on the receiving tier, alerting on 4xx (configuration errors) separately from 5xx and throttling.
- Transport parity test in CI: a golden payload exported over both transports to a staging receiver, confirming identical ingestion, guarding against drift when defaults change.

## Validation evidence

Evidence that the selected transport works as intended: a packet-level or access-log capture showing successful POSTs to the correct per-signal path (for HTTP) or successful gRPC methods with OK status; a throttling drill where the receiver returns 429/Retry-After (HTTP) or the throttling code (gRPC) and the exporter backs off visibly and then recovers, captured in the exporter's retry metrics; and the transport parity test output showing byte-identical semantic ingestion for the golden payload. For load-balancing claims, a distribution graph of requests per collector instance over a soak window, showing acceptable spread for the chosen transport and balancer.

## Failure modes and correction

- gRPC breaks behind an HTTP/1.1 proxy: streams cannot traverse. Switch the hop to OTLP/HTTP or terminate HTTP/2 at the proxy explicitly; do not attempt bidirectional streaming workarounds.
- All traffic lands on one collector with gRPC: L4 balancing without HTTP/2 awareness. Introduce an L7 balancer or a gateway tier, and verify the per-instance distribution graph.
- 404s on OTLP/HTTP: wrong endpoint path (missing `/v1/traces` suffix or per-signal endpoints not configured on the exporter). Correct the endpoint URL; the access log pinpoints it.
- Silent partial loss: the receiver returned partial success (some items rejected) and the exporter logged but did not retry. Enable partial-success logging and alert on its counter for either transport.
- JSON payloads in production by accident: someone flipped the encoding for debugging and left it. The compression/CPU or payload-size monitoring catches the regression; restore protobuf.
- Double compression CPU cost: compression enabled on a hop that did not need it. Re-measure and disable per the link's constraint.

## Limitations

Default ports (4317/4318) are conventions, not guarantees; deployments remap them, so endpoint configuration must always be explicit. Proxy behavior for HTTP/2 varies by product and configuration, so gRPC traversal claims must be tested on the actual intermediary. The JSON encoding's schema stability is good but its size cost is large at volume. This article does not cover WebSocket or streaming extensions, nor authentication frameworks beyond noting that both transports support the Collector's auth extensions. Performance comparisons between the transports depend on payload shape, compression, and kernel behavior; measure rather than cite generic numbers.

## Canonical sources

- OTLP specification (transports, endpoints, status codes, throttling): https://opentelemetry.io/docs/specs/otlp/
- OpenTelemetry Collector configuration (receivers, exporters, extensions): https://opentelemetry.io/docs/collector/configuration/
