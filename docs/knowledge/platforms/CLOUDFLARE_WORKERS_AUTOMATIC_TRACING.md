# Cloudflare Workers Automatic Tracing

## Purpose

Cloudflare Workers provides automatic distributed tracing that can show how a request moves through a Worker and connected services. Current Workers tracing does not require application SDK instrumentation for supported operations; tracing can be enabled through Worker observability configuration.

## Current tracing model

Cloudflare automatically captures spans for supported Worker handlers, `fetch()` requests, and many platform bindings such as KV, R2, and Durable Objects. Common span attributes can include Worker identity, invocation ID, version, Cloudflare data center, region, script tags, and operation-specific metadata.

Tracing is useful for diagnosing latency, understanding request fan-out, and correlating failures across platform services.

## Governance pattern

1. Enable tracing intentionally rather than assuming every environment needs the same volume.
2. Define sampling appropriate to traffic volume, debugging needs, and downstream storage cost.
3. Review captured span attributes before enabling export to external telemetry systems.
4. Avoid placing secrets, tokens, or unnecessary personal data in URLs, custom attributes, or other values that may become trace metadata.
5. Preserve deployment-version identifiers so traces can be connected to the Worker revision that produced them.
6. Use traces alongside logs and metrics; no single telemetry source should be treated as complete incident evidence.
7. Reassess instrumentation coverage after adding new Worker bindings or service-to-service calls.

## Automatic instrumentation boundary

Automatic tracing records supported operations known to the Workers runtime. Application-specific logical operations may still require explicit logs or custom telemetry if operators need visibility beyond the automatically emitted spans.

Do not assume the absence of a span proves that an operation did not occur unless the relevant runtime operation is documented as instrumented.

## Export and retention

Workers traces can be inspected in Cloudflare observability tooling and can also be exported through OpenTelemetry-compatible paths where configured. Export, sampling, and retention should be governed independently because an external observability provider can create a second data-retention boundary.

## Failure modes

- Enabling full tracing on high-volume traffic without sampling can increase observability cost.
- Treating automatic instrumentation as complete application tracing can leave custom business operations invisible.
- Logging or tracing sensitive values can propagate them to multiple telemetry systems.
- Comparing traces across deployments without version information can misattribute regressions.
- Assuming trace export includes Worker metrics is incorrect; current OTel export support is documented separately for traces and logs.

## Sources

- Cloudflare Workers Docs — Traces: https://developers.cloudflare.com/workers/observability/traces/
- Cloudflare Workers Docs — Spans and attributes: https://developers.cloudflare.com/workers/observability/traces/spans-and-attributes/
- Cloudflare Workers Docs — Exporting OpenTelemetry Data: https://developers.cloudflare.com/workers/observability/exporting-opentelemetry-data/

## Scope note

Cloudflare instrumentation coverage and trace attributes can change as the platform evolves. Verify current Workers documentation before relying on a specific span or field for automated policy.