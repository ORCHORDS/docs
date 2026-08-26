# grafana-dashboard-as-code

**Issue:** Managing Grafana dashboards in version control instead of the UI to enable review and rollback
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Dashboards are created in the Grafana UI and never exported. Engineers make ad-hoc changes that break panels. There is no history of who changed what, and no way to reproduce dashboards in a new environment.

## Pattern / Solution
Use Grafonnet (Jsonnet library), Grafana's provisioning system, or Terraform to keep dashboards in Git.

**Option A — Provisioning via YAML sidecar (simplest):**
```yaml
# /etc/grafana/provisioning/dashboards/default.yaml
apiVersion: 1
providers:
  - name: default
    type: file
    disableDeletion: true      # prevent UI deletion
    updateIntervalSeconds: 30
    allowUiUpdates: false      # warn when UI changes are not saved
    options:
      path: /var/lib/grafana/dashboards
      foldersFromFilesStructure: true
```

Place exported JSON files under `/var/lib/grafana/dashboards/`. Grafana hot-reloads them every 30 s.

**Export a dashboard as JSON:**
```bash
# Via API
curl -s -u admin:admin "http://localhost:3000/api/dashboards/uid/<uid>" \
  | jq '.dashboard' > dashboards/my-service.json
```

**Option B — Grafonnet (Jsonnet):**
```jsonnet
// dashboards/api-overview.jsonnet
local grafana = import 'grafonnet/grafana.libsonnet';
local dashboard = grafana.dashboard;
local row = grafana.row;
local prometheus = grafana.target.prometheus;
local graph = grafana.graphPanel;

dashboard.new('API Overview', schemaVersion=36, tags=['api'])
.addPanel(
  graph.new('Request Rate')
  .addTarget(prometheus.target(
    'sum(rate(http_requests_total[5m])) by (job)',
    legendFormat='{{job}}'
  )),
  gridPos={ h: 8, w: 12, x: 0, y: 0 }
)
```

```bash
# Compile Jsonnet to JSON
jsonnet -J vendor dashboards/api-overview.jsonnet -o output/api-overview.json
```

**Option C — Terraform (grafana provider):**
```hcl
resource "grafana_dashboard" "api_overview" {
  config_json = file("${path.module}/dashboards/api-overview.json")
  folder      = grafana_folder.infra.id
  overwrite   = true
}
```

## Gotchas
- `disableDeletion: true` prevents Grafana from removing provisioned dashboards if the file is deleted from the provisioning path — you must remove it from the UI separately.
- Dashboard UIDs must be stable and unique; regenerated UIDs break bookmark links and alert annotations.
- Grafana versions sometimes change the dashboard JSON schema; always test exports against the target Grafana version.
- Panels referencing library panels or variables not defined in the JSON will silently render empty.

## Related
- `prometheus-alertmanager-config.md`
- `opentelemetry-collector-config.md`
- `infrastructure-drift-remediation.md`
