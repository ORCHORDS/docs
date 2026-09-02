# CNCF Prometheus Operator Observability Governance

## Purpose

The Prometheus Operator, a CNCF project, manages Prometheus instances and related resources (ServiceMonitors, PodMonitors, PrometheusRules, AlertManagers) on Kubernetes. Governance ensures that observability is consistent across clusters, that alerts are actionable, and that storage and retention match the workload.

## Current context and source status

The Prometheus Operator is a CNCF project maintained by the Prometheus community. Versions and API resources (ServiceMonitor, PodMonitor, Probe) evolve; verify the current operator documentation and the CRD version before treating any specific resource as a current requirement.

## Governance workflow and controls

### 1. Adopt the operator

Adopt the Prometheus Operator for new Kubernetes clusters. Define cluster-level Prometheus instances per monitoring requirement (cluster monitoring, workload monitoring, application monitoring).

### 2. Define ServiceMonitors and PodMonitors

Define ServiceMonitors and PodMonitors for each workload. Apply label conventions. Document the scrape targets.

### 3. Define recording rules

Define recording rules for common aggregations. Apply naming conventions. Document the rule purpose.

### 4. Define alerting rules

Define alerting rules in PrometheusRule resources. Apply severity labels. Route alerts to the appropriate receiver.

### 5. Configure AlertManager

Configure AlertManager:

- routing by label;
- grouping rules;
- inhibition rules;
- silencing rules;
- receivers (Slack, PagerDuty, email, webhook).

Apply a documented routing tree.

### 6. Manage storage and retention

Manage Prometheus storage and retention per the workload's requirements. Apply remote write to long-term storage (Thanos, Cortex, Mimir) for cross-cluster aggregation.

### 7. Implement federation or remote write

Implement federation or remote write for cross-cluster aggregation. Apply authentication and authorization.

### 8. Apply high availability

Apply high availability for Prometheus and AlertManager. Use at least two replicas for production. Test failover.

## Validation and evidence

- Prometheus configuration.
- ServiceMonitor and PodMonitor inventory.
- Recording rules and alerting rules.
- AlertManager configuration.
- Storage and retention policy.

## Failure correction

Common defects include missing scrape targets, misconfigured alerts (too noisy, too quiet), and missing high availability. Corrective actions include a target inventory audit, an alert tuning exercise, and an HA deployment review.

## Limitations

- Prometheus Operator is specific to Kubernetes.
- Some metrics are not scrapeable without instrumentation.
- Long-term storage requires additional infrastructure.
- AlertManager configuration can become complex; maintain routing tree documentation.

## Canonical sources

- CNCF, Prometheus Operator documentation, current edition.
- CNCF, Prometheus documentation, current edition.
- CNCF, AlertManager documentation, current edition.

## Scope note

This article belongs to the engineering leaf and cross-references the platforms leaf for Kubernetes platforms, the operations leaf for alerting, and the security leaf for observability access control.
