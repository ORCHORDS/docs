# Grafana Dashboard Adoption Playbook

## Purpose
Provide a repeatable procedure for adopting and publishing Grafana
dashboards so teams can deliver consistent visualization, ownership,
and lifecycle management across the observability platform.

## Audience
Service owners publishing dashboards, platform engineers operating
Grafana, and reliability engineers integrating dashboards into
incident response workflows.

## Pre-conditions
- Grafana instance deployed and reachable from the target environment
  per the Grafana version governance card.
- Data sources (Prometheus, Loki, Tempo, or others) configured and
  accessible from the Grafana tenant.
- Dashboard ownership and on-call rotation recorded in the service
  catalog.
- Dashboard naming, tagging, and folder conventions agreed with the
  observability platform owner.
- Change management approval captured for any dashboard promoting
  alert-relevant panels.

## Procedure
1. Confirm the Grafana version is on the supported release line per
   the Grafana version governance card.
2. Author the dashboard JSON against the agreed template and validate
   it against the provisioning linter in the staging Grafana tenant.
3. Provision the dashboard through the configuration repository so it
   can be reviewed, versioned, and rolled back alongside the
   application.
4. Tag the dashboard with the owning service, severity tier, and
   incident-response role so responders can locate it during on-call.
5. Link the dashboard from the service runbook, alerting runbook, and
   any incident postmortem templates associated with the service.
6. Validate the dashboard renders against synthetic traffic and that
   each panel query returns within the agreed latency budget.
7. Schedule a review cadence aligned with the Grafana version
   governance review cycle and the service lifecycle.
8. Document the rollout, owners, and known gaps in the service
   observability runbook before declaring adoption complete.

## Rollback
- Remove the dashboard JSON from the provisioning bundle and re-run
   the configuration pipeline to drop it from Grafana.
- Restore the previous dashboard JSON from version control if the
  removal triggers regressions in dependent panels or links.
- Confirm dependent runbooks, alerts, and postmortem templates no
  longer reference the rolled-back dashboard.
- Capture the failure mode in the post-incident review and update
  this playbook with any newly identified guardrails.

## References
- [Grafana version governance](../reference/GRAFANA_VERSION_GOVERNANCE.md)
- [Prometheus version governance](../reference/PROMETHEUS_VERSION_GOVERNANCE.md)
- [Jaeger version governance](../reference/JAEGER_VERSION_GOVERNANCE.md)
- [Service mesh mTLS rollout playbook](SERVICE_MESH_MTLS_ROLLOUT_PLAYBOOK.md)
