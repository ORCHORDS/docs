---
title: Grafana Observability Platform Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://github.com/grafana/grafana
---

# Grafana Observability Platform Version Governance

## Purpose
Define how teams select, upgrade, and operate Grafana deployments so
dashboards, alerting, and data source integrations remain supported,
secure, and aligned with downstream observability backends.

## Scope
Applies to Grafana OSS, Grafana Enterprise, and managed Grafana
offerings used for visualization, alerting, and incident response
across development, staging, and production environments.

## Version Line Policy
- Track the latest stable major release for at least 90 days before
  declaring it production-ready.
- Hold one previous major release available for rollback for at least
  30 days after promotion.
- Skip releases that ship breaking data source, plugin, or
  provisioning API changes without an internal exception record.
- Align Grafana version with the version of the Grafana Agent or
  OpenTelemetry Collector shipping telemetry into the platform.

## Component Lifecycle
- Core data sources progress through `beta` to `GA` per the upstream
  maturity model.
- Plugins from the Grafana plugin marketplace follow the published
  compatibility matrix; unsupported plugins are not approved for
  production dashboards.
- Alerting and unified alerting features are governed by the Grafana
  alerting maturity track; legacy alerting is deprecated per upstream
  notice.
- Provisioning APIs and dashboard JSON schemas evolve per major
  release and require coordinated migration.

## Compatibility Considerations
- Data source backends (Prometheus, Loki, Tempo, Mimir,
  Elasticsearch, CloudWatch, and others) must be on versions supported
  by the chosen Grafana line.
- Authentication providers must support the configured OAuth, OIDC,
  SAML, or LDAP flows.
- Dashboard and alert provisioning must remain compatible with the
  configuration management tooling in use across environments.
- TLS, mTLS, and header-based integrations must interoperate with the
  platform identity provider and ingress layer.

## Upgrade Procedure
1. Read upstream release notes and identify breaking changes affecting
   data sources, alerting, provisioning, or authentication.
2. Validate the new release in a staging environment with a snapshot
   of production dashboards, alert rules, and provisioning
   configuration.
3. Run a canary upgrade for a single Grafana instance behind the load
   balancer and verify dashboards render, alerts evaluate, and data
   source queries succeed.
4. Promote the upgrade across remaining instances with pre-staged
   rollback artifacts and on-call coverage.
5. Record the upgrade window, observed deltas, and any compensating
   configuration changes in the change log.

## Rollback Procedure
- Re-deploy the previous Grafana image and configuration from the
  versioned artifact store.
- Restore the prior provisioning bundle so dashboards, data sources,
  and alert rules match the pre-upgrade state.
- Re-validate authentication, alert evaluation, and data source
  connectivity against the synthetic probes.
- Open a regression ticket capturing the cause of the rollback and
  link it to the originating upgrade record.

## Security Considerations
- Pin Grafana images by digest and verify signatures using the
  container trust store.
- Restrict admin API access to break-glass operators and require
  approval before privilege escalation.
- Use external auth providers and disable local admin accounts outside
  break-glass scenarios.
- Scrub sensitive data from dashboard variables, annotations, and
  alert message templates before publishing.

## Operational Impact Points
- Upgrades restart the Grafana process and may drop in-flight
  alerting evaluations; alertmanager handles retry.
- Dashboard-heavy instances benefit from provisioned data sources and
  alert rules to reduce boot time.
- Shared SQLite or metadata databases require migration planning per
  major release.
- High availability deployments must keep provisioning in version
  control to avoid drift between instances.

## Cross-References
- See [Prometheus version governance](PROMETHEUS_VERSION_GOVERNANCE.md).
- See [OpenTelemetry Collector Contrib governance](OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md).
- See [Google SRE release engineering](GOOGLE_SRE_RELEASE_ENGINEERING.md).

---

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
