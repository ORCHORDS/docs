# Cloudflare Workers OpenTelemetry Export

## Purpose

Cloudflare Workers can export OpenTelemetry-compatible traces and logs to external observability systems through OTLP endpoints. This lets a Worker deployment integrate with an existing monitoring stack while retaining Cloudflare's built-in telemetry generation.

Cloudflare's current documentation, updated August 4, 2026, lists traces and logs as supported export types. Worker metrics and custom metrics are not currently supported by this export path.

## Export model

Cloudflare can export:

- distributed traces showing request flow through a Worker and connected services; and
- application and system logs, including `console.log()` output.

Destinations must expose compatible OpenTelemetry endpoints. Authentication headers and endpoint details vary by provider.

## Governance pattern

1. Decide whether telemetry should remain only in Cloudflare, be exported externally, or use both paths.
2. Separate trace and log endpoint configuration when the destination uses different OTLP endpoints.
3. Store destination credentials as managed secrets rather than plaintext configuration.
4. Minimize sensitive data before it reaches logs or spans; export does not make unsafe telemetry safe.
5. Define sampling and retention at both the Cloudflare and destination layers so duplicated retention does not become accidental policy.
6. Monitor export failures independently from Worker application failures.
7. Document the destination account, region, retention policy, and operational owner.
8. Revalidate the integration after provider endpoint, authentication, or telemetry-schema changes.

## Traces versus logs

Traces are intended to explain the flow and timing of a request across handlers, fetches, and supported bindings. Logs contain application-generated and platform-generated log events. They serve different investigation purposes and should not be assumed to have identical sampling, retention, or field availability.

## Security and privacy

Telemetry may contain URLs, request metadata, identifiers, exception text, and application-provided log values. Treat export as a data transfer to another processor or service boundary.

Recommended controls include:

- avoiding secrets and authentication tokens in console output;
- redacting or hashing identifiers when raw values are unnecessary;
- restricting OTLP credentials to telemetry ingestion only;
- validating TLS endpoints and destination ownership; and
- applying destination-side access and retention controls proportionate to the data.

## Failure modes

- Assuming metrics are exported through the same Workers OTLP mechanism is currently incorrect.
- Exporting every log field without review can increase privacy and cost exposure.
- Treating telemetry-export failure as application failure can create unnecessary request coupling.
- Keeping destination tokens in source-controlled configuration exposes credentials.
- Enabling traces without monitoring volume can produce unexpected downstream ingestion costs.

## Sources

- Cloudflare Workers Docs — Exporting OpenTelemetry Data: https://developers.cloudflare.com/workers/observability/exporting-opentelemetry-data/
- Cloudflare Workers Docs — Observability: https://developers.cloudflare.com/workers/observability/

## Scope note

Supported telemetry types, endpoint formats, and observability features can change. Verify current Cloudflare and destination-provider documentation before using export configuration as an assurance or cost assumption.