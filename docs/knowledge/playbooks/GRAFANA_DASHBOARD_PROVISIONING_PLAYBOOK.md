# Grafana Dashboard Provisioning Playbook

## Purpose

Define the operational procedure for provisioning Grafana dashboards, data sources, and alerting rules from files (GitOps) rather than the UI. The procedure ensures dashboards are reproducible and reviewed.

## Audience

Platform engineers, SREs, and observability engineers.

## Pre-conditions

- Grafana 10+ (per `GRAFANA_VERSION_GOVERNANCE.md`).
- The Grafana instance has a `provisioning/` directory mounted.
- The team has access to the dashboard repository.

## Procedure

### Step 1 — Author

1. Author dashboards in JSON format (export from existing dashboards).
2. Place files in `dashboards/<service>/<name>.json`.
3. Author data sources in YAML: `provisioning/datasources/<name>.yaml`.
4. Author alerting rules in YAML: `provisioning/alerting/<name>.yaml`.

### Step 2 — Lint

5. Validate JSON schema: `python -c 'import json; json.load(open("dashboard.json"))'`.
6. Validate YAML schema: `yq eval`.
7. Confirm the schema version is supported by the target Grafana.

### Step 3 — Push

8. Commit to the dashboard repository.
9. Push the branch.
10. Open a PR for review.
11. Merge after approval.

### Step 4 — Apply

12. Grafana hot-reloads the `provisioning/` directory every 30 seconds.
13. Or trigger via the admin API: `POST /api/dashboards/import`.
14. Confirm the dashboard appears in the UI.

### Step 5 — Verify

15. Confirm the data source connection works.
16. Confirm the queries return data.
17. Confirm the alerts evaluate correctly.

### Step 6 — Cleanup

18. Remove unused dashboards.
19. Archive old versions in the repository.

## Rollback

If a provisioned dashboard breaks:

1. Revert the commit.
2. Confirm Grafana reverts the dashboard.
3. Investigate the regression.

## References

- `GRAFANA_VERSION_GOVERNANCE.md`
- `GITOPS_SYNC_FAILURE_RECOVERY_PLAYBOOK.md`
- Grafana provisioning: `https://grafana.com/docs/grafana/latest/administration/provisioning/`
- Grafana HTTP API: `https://grafana.com/docs/grafana/latest/developers/http_api/`
