# w3c-trace-context-propagation

**Issue:** Distributed traces across the example project stack break silently at service boundaries because not every hop speaks the same propagation format. The mobile app injects a B3 header, the Cloudflare Worker forwards only `traceparent`, an upstream vendor gateway strips unknown headers entirely, and the resulting "traces" in the backend are three disconnected fragments. The team needs one canonical wire format for trace context — W3C Trace Context (`traceparent`/`tracestate`) — plus explicit rules for ingress parsing, egress injection, proxy behavior, and fallback when a peer does not support it.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Header anatomy and parsing rules

1. **`traceparent` is four fields, one string.** Format is `version-traceid-parentid-traceflags`, e.g. `00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01`. Version `00` is fixed-width; parsers must read it positionally, never by splitting on `-` and hoping, because future versions may change layout.
2. **Reject malformed headers and start a new trace.** Per the W3C spec, if `traceparent` fails validation (wrong lengths, uppercase hex, unknown-but-invalid shapes), the receiver must ignore it and generate a fresh trace ID rather than attempt repair. Log the rejection at debug level with a hash of the offending value — silently "fixing" headers produces phantom parent spans that poison latency math.
3. **Treat headers as untrusted input.** The spec's security considerations explicitly warn that `traceparent`/`tracestate` arrive from potentially malicious parties. Cap total `tracestate` size (spec limit 512 bytes per entry list enforcement is vendor-side), reject entries over the per-entry limit, and never parse header values with regexes vulnerable to catastrophic backtracking.
4. **`tracestate` is for vendor/system state, not business data.** It is a comma-separated list of `vendorkey=value` entries that multiple tracing systems append to. Use it for things like sampling decisions (`cw-ae=1`) that cooperating systems need to read in-flight. Tenant IDs, flags, and user data belong in W3C Baggage, which is a separate, parallel header — never smuggle them into `tracestate`.
5. **Unknown version: forward `tracestate` but regenerate `traceparent` when modifying.** If the incoming version is above what you support (e.g. `ff-...`), you may pass the message through untouched, but if your service emits spans or downstream calls it must restart with a new valid `traceparent` and preserve `tracestate` entries it does not own.

## Making OTel use W3C propagation everywhere

1. **Set the global propagator explicitly.** OpenTelemetry defaults to W3C TraceContext + Baggage in current SDK versions, but do not rely on the default — register it in code so an SDK upgrade or a framework auto-init cannot swap it out: `otel.SetTextMapPropagator(new CompositePropagator({ contexts: [new W3CTraceContextPropagator(), new W3CBaggagePropagator()] }))`.
2. **Inject at every egress point, extract at every ingress point.** Manual HTTP calls, queue producers/consumers, and gRPC metadata all need explicit `propagation.inject(carrier)` / `propagation.extract(carrier)` calls when they are not covered by auto-instrumentation. The most common break in practice is a hand-rolled `fetch` inside an instrumented service that nobody annotated.
3. **Bridging B3 and W3C goes at the edge only.** Legacy services that only speak B3 (`x-b3-traceid` and friends) need a translating propagator (e.g. OTel's B3 propagator in single- or multi-header mode) deployed at the boundary service that talks to them. Do not enable dual-format propagation fleet-wide — dual injection doubles header bytes and creates ambiguity about which source of truth wins on extract.
4. **Verify propagation continuously, not once.** Add an integration test that issues a request through every hop of one canonical path and asserts the trace ID observed at the terminal service equals the ID injected at the origin. A weekly synthetic that walks the same path catches regressions from middleware upgrades, CDN config changes, and new proxies.

## Proxies, CDNs, and gateways that eat headers

1. **Cloudflare Workers forward `traceparent` by default — but subrequests to third parties do not carry it safely.** When the Worker calls a vendor API, inject `traceparent` only if the vendor documents W3C support; otherwise the header leaks your internal trace IDs to a third party. Strip it from cross-boundary egress with an explicit `delete headers['traceparent']`.
2. **Nginx/Envoy defaults can drop or mangle unknown headers.** Nginx underscore-header rewriting (`underscores_in_headers`) and Envoy's `pass_through_matcher` config both bite trace headers in odd ways. Assert header pass-through in staging with a curl harness before blaming the tracing vendor for "broken traces."
3. **Load balancer-generated traces double your spans.** Some ALBs and service meshes create their own span on extract and become the span parent, which is correct behavior but surprises teams comparing service maps. Confirm whether your LB participates in tracing and account for its extra hop in latency waterfall analysis.
4. **Message queues need the context in the message body or properties.** `traceparent` must be mapped into SQS message attributes, Kafka headers, or AMQP properties by the producer, and extracted by the consumer — the queue itself will never propagate HTTP headers. Without this, async edges are permanently dark.

## Operational verification and failure modes

1. **Trace-ID parity is the acceptance criterion.** Log `trace_id` as a structured field on every log line (see `log-correlation-ids.md`) and alert when sampled requests show log records whose trace IDs never appear in the trace backend — that divergence localizes the broken hop in minutes.
2. **Watch for all-zero or obviously fake trace IDs.** `00000000000000000000000000000000` trace IDs or sequential IDs indicate a library generating non-conforming IDs; W3C Level 2 tightened randomness requirements precisely because weak IDs collide at scale and merge unrelated traces.
3. **Keep one propagation-format decision record.** Document in the repo which format each service speaks, where translation happens, and which egress paths strip context. When a new service is onboarded, the record answers "which propagator do I configure" without archaeology.
4. **Budget header overhead.** `traceparent` is ~70 bytes and `tracestate` can legally grow with vendor entries across hops; audit total added header bytes per request path so p99 latency and per-request cost do not creep up unnoticed on high-fanout calls.
