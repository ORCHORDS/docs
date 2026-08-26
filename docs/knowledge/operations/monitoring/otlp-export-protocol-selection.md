# otlp-export-protocol-selection

**Issue:** The OpenTelemetry Protocol (OTLP) ships over two transports: OTLP/gRPC (HTTP/2 with protobuf framing and RPC semantics) and OTLP/HTTP (typically protobuf over POST requests, with JSON as an option). Every SDK exporter, collector, and backend connection must pick one, and the choice has real operational consequences: gRPC's long-lived HTTP/2 connections defeat naive layer-4 load balancing and get blocked by corporate proxies and some k8s ingress setups, while plain HTTP traverses any load balancer, CDN, or proxy but gives up flow control and gRPC-style deadline propagation. Retry behavior also differs — gRPC exporters retry on retryable status codes, while HTTP exporters honor 429/503 responses and Retry-After headers. Teams that pick by coin flip discover the failure modes during an outage. The engineering problem is choosing the transport per hop (app to agent, agent to gateway, gateway to backend) based on the network path and failure semantics, and pairing either choice with queueing so telemetry survives backend hiccups.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How the two transports differ

1. **Connection model.** gRPC multiplexes many concurrent exports over long-lived HTTP/2 connections, which is efficient for high-throughput streaming but means a load balancer that balances per-connection will pin all traffic from one app instance to one collector; OTLP/HTTP uses ordinary requests that every L7 balancer, ingress, and CDN distributes evenly.
2. **Retry semantics.** Per the OTLP specification, gRPC exporters retry on retryable gRPC status codes with exponential backoff, while HTTP exporters treat 429 and 503-class responses as retryable and respect Retry-After headers; both must not retry non-retryable failures.
3. **Flow control and delivery.** OTLP/gRPC inherits HTTP/2 flow control, which gives the receiving collector a way to apply backpressure to a fast sender instead of buffering unboundedly, a property valuable for guaranteed log delivery under load.
4. **Ecosystem drift.** Some clients have already dropped gRPC support (the .NET Framework OTLP exporter is HTTP-only), so mixed fleets increasingly standardize on OTLP/HTTP to keep one export path everywhere.

## Choosing per hop

1. **App to local agent: either, gRPC slightly favored.** The hop to a same-host or same-pod agent (sidecar or daemonset) crosses no proxies, so gRPC's connection efficiency and flow control pay off with none of its traversal downsides.
2. **Agent to gateway across the cluster or internet: HTTP.** This path crosses ingresses, service meshes, API gateways, and corporate proxies where gRPC needs special configuration (grpc ingress annotations, TLS ALPN) or silently fails; OTLP/HTTP on port 4318 works through stock infrastructure, including gzip compression and headers-based auth.
3. **Gateway to vendor backend: follow the vendor.** Most vendors accept both; prefer the transport their docs recommend for retry and auth behavior, and keep the collector's exporterhelper queue and retry configuration as the real reliability layer regardless of transport.
4. **Browser and constrained clients: HTTP only.** OTLP/HTTP with JSON payloads is the only realistic option from web or edge runtimes that cannot speak HTTP/2 gRPC, which is another reason HTTP skills transfer well across the fleet.

## Operational hardening

1. **Load balance gRPC correctly or not at all.** If you run OTLP/gRPC behind a balancer, it must be gRPC-aware (per-request L7 balancing as Envoy provides); otherwise shards pile onto one collector while others idle, and you find out at peak.
2. **Enable compression on both.** Protobuf payloads compress well; gzip (or zstd where supported) on the exporter cuts egress cost substantially at high log volume, and the CPU trade is almost always worth it.
3. **Always pair with sending_queue and retry.** Whichever transport wins, configure the collector exporter's queue_size, retry_on_failure, and ideally a persistent queue (file_storage extension) so a backend outage degrades into delayed telemetry instead of dropped telemetry.
4. **Size timeouts against your SLO for telemetry, not hope.** Set exporter timeouts so a wedged backend fails fast enough for the queue to absorb, and monitor queue depth and failed-send metrics rather than assuming delivery.

## Verification checklist

1. **Test the full network path.** Verify export through the real ingress/proxy chain with TLS, mTLS, and auth headers in place; gRPC failures frequently appear only behind the exact middleware combination of production.
2. **Fail the backend on purpose.** Stop the receiving backend and confirm retries fire, the queue fills at a visible rate, and nothing is silently dropped before the configured limits.
3. **Watch accept headers and content negotiation.** OTLP/HTTP receivers must accept protobuf; a misconfigured proxy that strips content-type or re-encodes the body produces 400s that look like SDK bugs.
4. **Document the decision per hop.** Record which transport each tier uses and why, so the next service adopts the fleet standard instead of reopening the debate with less context.
