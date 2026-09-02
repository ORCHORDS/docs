# CNCF OpenTelemetry Observability Governance

## Purpose

OpenTelemetry is a CNCF Incubating project that provides vendor-neutral APIs, SDKs, and tools for generating and collecting telemetry data (metrics, logs, traces). It merges the OpenTracing and OpenCensus projects. Governance ensures that applications emit OpenTelemetry telemetry consistently, that the collector is configured for the organization's needs, and that telemetry data is used responsibly.

## Current context and source status

OpenTelemetry is a CNCF Incubating project. The project includes specifications, SDKs in multiple languages, the OpenTelemetry Collector, and the OpenTelemetry Protocol (OTLP). Specifications and APIs evolve; verify the current OpenTelemetry documentation and the language SDK maturity before treating any specific signal or API as stable.

## Governance workflow and controls

### 1. Adopt OpenTelemetry as the telemetry standard

Adopt OpenTelemetry as the standard for telemetry emission across applications. Migrate from legacy agents and SDKs where practical.

### 2. Apply language SDKs

Apply the OpenTelemetry language SDKs in applications. Configure:

- resource attributes (service.name, service.version, deployment.environment);
- instrumentation libraries (HTTP, gRPC, database, messaging);
- exporters (OTLP to the collector);
- propagators (W3C Trace Context).

### 3. Configure the OpenTelemetry Collector

Configure the OpenTelemetry Collector:

- receivers (OTLP, Prometheus, Zipkin, Jaeger);
- processors (batch, attributes, memory limiter, tail-based sampling);
- exporters (OTLP, Prometheus remote write, logging).

Apply a documented configuration.

### 4. Manage resource attributes

Manage resource attributes consistently. Apply a documented attribute schema. Document attribute usage.

### 5. Apply sampling

Apply sampling for traces. Apply head-based sampling for low-cost collection or tail-based sampling for capturing errors and slow traces. Document the sampling strategy.

### 6. Manage telemetry data privacy

Manage telemetry data privacy:

- apply data minimization;
- redact sensitive attributes;
- restrict access to telemetry data;
- apply retention rules.

### 7. Integrate with backends

Integrate the collector with backends (Jaeger, Tempo, Prometheus, commercial APMs). Use OTLP where supported.

## Validation and evidence

- SDK adoption evidence.
- Collector configuration.
- Sampling configuration.
- Privacy configuration.

## Failure correction

Common defects include inconsistent resource attributes, missing sampling, and sensitive data in telemetry. Corrective actions include a resource attribute validation, a sampling review, and a privacy audit.

## Limitations

- OpenTelemetry maturity varies by language.
- Some legacy applications cannot be instrumented without modification.
- Tail-based sampling requires additional compute.
- Telemetry data is sensitive and must be handled accordingly.

## Canonical sources

- CNCF, OpenTelemetry documentation, current edition.
- CNCF, OpenTelemetry specification, current edition.
- CNCF, OpenTelemetry Collector configuration reference, current edition.

## Scope note

This article belongs to the engineering leaf and cross-references the platforms leaf for observability platforms, the operations leaf for incident response, and the security leaf for telemetry data privacy.
