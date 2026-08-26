# OpenTelemetry Collector zPages access boundaries

**Issue:** Collector zPages aid live diagnosis but can expose internal spans, service names, attributes, and topology if bound to an untrusted interface.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Enable the zPages extension only for a defined diagnostic need, bind it to loopback or a protected management interface, and restrict network access independently of application ingress. Do not publish it through a public load balancer. Review telemetry attribute policy because diagnostic pages can surface data received before downstream redaction. Disable the extension where operational access is not required.

## Verification

From the approved administration path, confirm required pages work during a disposable trace test. From an untrusted network segment, prove the endpoint is unreachable. Inspect displayed attributes for secrets, personal data, and high-cardinality identifiers, then test configuration rollback.

## Gotchas

Network restriction does not sanitize content, and zPages are not a durable telemetry store. Binding to all interfaces for convenience creates an observability data leak even when the application's primary endpoints are authenticated.

## Official sources

- https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/extension/zpagesextension
- https://opentelemetry.io/docs/collector/configuration/#extensions
