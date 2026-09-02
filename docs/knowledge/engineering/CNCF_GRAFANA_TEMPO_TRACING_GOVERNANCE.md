# CNCF Grafana Tempo Distributed Tracing Governance

## Purpose

Grafana Tempo is a CNCF Incubating project for distributed tracing. Tempo is designed for high-volume, low-cost trace storage and integrates with Grafana, Prometheus, and Loki. Governance ensures that trace collection is consistent, that sampling reflects the workload's needs, and that trace storage is managed for cost and retention.

## Current context and source status

Grafana Tempo is a CNCF Incubating project. Features and integrations evolve; verify the current Tempo documentation and the supported protocols (OpenTelemetry, Jaeger, Zipkin) before treating any specific configuration as a current requirement.

## Governance workflow and controls

### 1. Adopt the tracing protocol

Adopt OpenTelemetry as the tracing protocol. Where legacy applications use Jaeger or Zipkin, configure Tempo receivers accordingly.

### 2. Configure trace collection

Configure trace collection at the application level using OpenTelemetry SDKs. Apply resource attributes (service.name, service.version, deployment.environment).

### 3. Configure sampling

Configure sampling per the workload:

- head-based sampling for low-cost collection;
- tail-based sampling for capturing all errors and slow traces.

Document the sampling strategy.

### 4. Configure trace storage

Configure trace storage (S3, GCS, Azure Blob) with appropriate retention. Apply lifecycle policies.

### 5. Integrate with Grafana

Integrate with Grafana for trace visualization. Apply Grafana data source configuration. Use trace-to-log and trace-to-metrics correlation.

### 6. Implement search and discovery

Implement search and discovery using Tempo's search capabilities. Apply service map generation.

### 7. Apply access control

Apply access control to Tempo queries. Restrict sensitive traces. Apply retention rules per service.

### 8. Manage costs

Manage costs through sampling, retention, and trace filtering. Apply cost monitoring.

## Validation and evidence

- Trace collection configuration.
- Sampling configuration.
- Trace storage configuration.
- Grafana integration.
- Access control configuration.

## Failure correction

Common defects include missing resource attributes, inadequate sampling, and uncontrolled retention. Corrective actions include a resource attribute verification, a sampling review, and a retention policy enforcement.

## Limitations

- Tempo is designed for high volume; some legacy features (e.g., Jaeger UI) are not available.
- Tail-based sampling requires additional compute resources.
- Trace storage costs scale with retention.
- OpenTelemetry SDK adoption requires application changes.

## Canonical sources

- CNCF, Grafana Tempo documentation, current edition.
- CNCF, OpenTelemetry documentation, current edition.

## Scope note

This article belongs to the engineering leaf and cross-references the platforms leaf for observability platforms, the operations leaf for incident triage, and the security leaf for observability access control.
