# Prometheus Alerting Adoption Playbook

## Purpose
Provide a repeatable procedure for adopting and managing Prometheus
alert rules and Alertmanager configuration so teams can deliver
consistent, actionable alerts integrated with downstream
notification and incident response workflows.

## Audience
Service owners authoring alert rules, platform engineers operating
Prometheus and Alertmanager, and reliability engineers integrating
alerts into on-call workflows.

## Pre-conditions
- Prometheus and Alertmanager deployed and reachable from the target
  environment per the Prometheus version governance card.
- Recording rules and alert rules authored against the agreed rule
  template and naming convention.
- Notification receivers (PagerDuty, Slack, email, webhook) configured
  with routing ownership per service tier.
- Alert routing and grouping policy approved by the incident response
  team.
- Synthetic load or canary workload available to validate alert
  evaluation.

## Procedure
1. Confirm the Prometheus and Alertmanager versions are on the
   supported release line per the Prometheus version governance card.
2. Author the alert rule against the agreed template and validate it
   with `promtool check rules` in the staging environment.
3. Provision the alert rule through the configuration repository so
   it can be reviewed, versioned, and rolled back alongside the
   application.
4. Configure Alertmanager routing to deliver the alert to the agreed
   notification receivers and on-call rotation.
5. Link the alert to the owning service runbook, dashboard, and any
   associated postmortem template so responders can pivot quickly.
6. Validate the alert fires under the agreed condition using
   synthetic traffic or a chaos exercise and that silencing works as
   documented.
7. Schedule a review cadence aligned with the Prometheus version
   governance review cycle and the service lifecycle.
8. Document the rollout, owners, and known gaps in the service
   observability runbook before declaring adoption complete.

## Rollback
- Remove the alert rule from the rule file bundle and re-run the
   Prometheus configuration reload to drop it from evaluation.
- Revert Alertmanager routing changes to the prior version if the new
  routing triggers duplicate or misdirected pages.
- Confirm dependent runbooks, dashboards, and postmortem templates no
  longer reference the rolled-back alert.
- Capture the failure mode in the post-incident review and update
  this playbook with any newly identified guardrails.

## References
- [Prometheus version governance](../reference/PROMETHEUS_VERSION_GOVERNANCE.md)
- [Grafana version governance](../reference/GRAFANA_VERSION_GOVERNANCE.md)
- [Jaeger version governance](../reference/JAEGER_VERSION_GOVERNANCE.md)
- [Service mesh mTLS rollout playbook](SERVICE_MESH_MTLS_ROLLOUT_PLAYBOOK.md)
