# Cloudflare Workers Logging Mode Selection

## Purpose

Cloudflare Workers offers several logging paths with different retention, sampling, transformation, and export behavior. Choosing the wrong mode can create gaps in incident evidence or unnecessary operational cost.

## Workers Logs

Workers Logs automatically collects, stores, filters, and analyzes invocation logs, custom logs, errors, and uncaught exceptions for a Worker. Cloudflare states that newly created Workers have observability enabled by default.

Use Workers Logs when retained, searchable logs are required for troubleshooting, analysis, and post-event review. Head-based sampling can reduce volume for high-traffic workloads, but the sampling decision should match the evidence and observability requirements of the workload.

## Real-time logs

Real-time logs are intended for immediate feedback during development, deployment, and active troubleshooting. They can be viewed from the dashboard or with `wrangler tail`.

Important limitations:

- real-time logs do not store Workers Logs;
- high traffic can cause real-time logs to enter sampling mode and drop messages; and
- they should not be treated as a complete historical audit source.

Use real-time logs for live diagnosis rather than long-term retention.

## Tail Workers

Tail Workers receive execution information from producer Workers after invocations and can apply custom filtering, transformation, alerting, or export logic. Cloudflare describes Tail Workers as an advanced-mode option for custom processing that is not built into the observability platform.

For common third-party observability exports, Cloudflare recommends considering OpenTelemetry export instead of building a Tail Worker merely to forward logs and traces.

## Selection pattern

1. Use **Workers Logs** for retained, searchable platform-native logs.
2. Use **real-time logs** for live operational feedback where some sampling under load is acceptable.
3. Use **OpenTelemetry export** for supported integrations that need batched external logs and traces.
4. Use **Tail Workers** when custom transformation, filtering, routing, or post-invocation processing is actually required.
5. Document sampling, retention, redaction, and export assumptions so an incident investigation does not depend on data that was never stored.

## Sources

- Cloudflare Workers Docs — Observability: https://developers.cloudflare.com/workers/observability/
- Cloudflare Workers Docs — Workers Logs: https://developers.cloudflare.com/workers/observability/logs/workers-logs/
- Cloudflare Workers Docs — Real-time logs: https://developers.cloudflare.com/workers/observability/logs/real-time-logs/
- Cloudflare Workers Docs — Tail Workers: https://developers.cloudflare.com/workers/observability/logs/tail-workers/

## Scope note

This article summarizes current public Cloudflare Workers observability modes. Availability, pricing, limits, retention, and feature behavior can change and should be checked against current Cloudflare documentation before implementation.