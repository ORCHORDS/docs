---
title: Prometheus Monitoring System Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://github.com/prometheus/prometheus
---

# Prometheus Monitoring System Version Governance

## Purpose
Define how teams select, upgrade, and operate Prometheus servers and
Alertmanager instances so metrics collection, storage, and alerting
remain supported, secure, and aligned with downstream visualization
and incident response tooling.

## Scope
Applies to Prometheus server, Alertmanager, and the official
exporters used to instrument infrastructure, applications, and
Kubernetes workloads across development, staging, and production
environments.

## Version Line Policy
- Track the latest stable minor release for at least 90 days before
  declaring it production-ready.
- Hold one previous minor release available for rollback for at least
  30 days after promotion.
- Skip releases with breaking changes to the storage engine, scrape
  protocol, or alert rule evaluation semantics without an internal
  exception record.
- Align Prometheus version with the version of the OpenTelemetry
  Collector or Prometheus Agent shipping metrics into the platform.

## Component Lifecycle
- Servers, alertmanagers, and exporters progress through the
  upstream stability ladder; experimental features are not permitted
  in production without an architecture-review exception.
- Remote-write receivers progress through the maturity ladder and
  require capacity validation before production enablement.
- Configuration file schema evolves per release and must be
  validated before promotion.
- Deprecated metrics, labels, and recording rule patterns must be
  removed within two minor release cycles.

## Compatibility Considerations
- Scrape protocol and exposition format must remain compatible with
  the monitored targets, including OpenMetrics 1.0 and 2.0 endpoints.
- Remote-write receivers and storage adapters must be on versions
  supported by the chosen backend (Thanos, Cortex, Mimir, or
  long-term storage).
- Alertmanager cluster protocol must interoperate with the chosen
  Alertmanager version and downstream notification integrations.
- TLS, mTLS, basic auth, and OAuth configuration must interoperate
  with the platform identity provider and ingress layer.

## Upgrade Procedure
1. Read upstream release notes and identify breaking changes affecting
   scrape configuration, storage, alert rules, or remote write.
2. Validate the new release in a staging environment with a snapshot
   of production scrape configuration and alert rules.
3. Run a canary upgrade for a single Prometheus shard and verify
   scrape continuity, remote-write success, and alert evaluation.
4. Promote the upgrade across remaining shards with pre-staged
   rollback artifacts and on-call coverage.
5. Record the upgrade window, observed deltas, and any compensating
   configuration changes in the change log.

## Rollback Procedure
- Re-deploy the previous Prometheus image and configuration from the
  versioned artifact store.
- Restore the prior rule files so evaluation matches the pre-upgrade
  state.
- Re-validate scrape success and remote-write flow against the
  synthetic probes.
- Open a regression ticket capturing the cause of the rollback and
  link it to the originating upgrade record.

## Security Considerations
- Pin Prometheus and Alertmanager images by digest and verify
  signatures using the container trust store.
- Restrict admin API and UI access to operators; require approval
  before privilege escalation.
- Use external auth providers and disable local admin accounts outside
  break-glass scenarios.
- Scrub sensitive labels from metrics before remote write to
  long-term storage.

## Operational Impact Points
- Upgrades restart the Prometheus process and may drop in-flight
  scrapes; targets re-scrape on the next interval.
- High-cardinality metrics and labels can degrade query performance;
  enforce cardinality budgets per target.
- WAL and TSDB retention trade disk usage for query and replay
  capability.
- Sharded deployments must keep global rule evaluation consistent to
  avoid alert duplication.

## Cross-References
- See [Grafana version governance](GRAFANA_VERSION_GOVERNANCE.md).
- See [OpenTelemetry Collector Contrib governance](OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md).
- See [Google SRE release engineering](GOOGLE_SRE_RELEASE_ENGINEERING.md).

---

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
