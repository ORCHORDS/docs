# helm-chart-best-practices

**Issue:** Structuring Helm charts for maintainability, safety, and reusability
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Poorly structured Helm charts become impossible to upgrade, break on values changes, and leak secrets. These patterns prevent the most common failures.

## Pattern / Solution
Chart layout:
```
mychart/
  Chart.yaml          # apiVersion, name, version, appVersion, dependencies
  values.yaml         # defaults — every value used in templates must be here
  values.schema.json  # JSON Schema validation for values
  templates/
    _helpers.tpl      # named templates and shared labels
    deployment.yaml
    service.yaml
    ingress.yaml
    hpa.yaml
    NOTES.txt         # post-install instructions
  charts/             # vendored sub-charts (helm dependency update)
```

`_helpers.tpl` canonical labels:
```yaml
{{- define "mychart.labels" -}}
helm.sh/chart: {{ include "mychart.chart" . }}
app.kubernetes.io/name: {{ include "mychart.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
```

values.schema.json snippet:
```json
{
  "$schema": "https://json-schema.org/draft-07/schema",
  "properties": {
    "replicaCount": { "type": "integer", "minimum": 1 },
    "image": {
      "type": "object",
      "required": ["repository", "tag"],
      "properties": {
        "repository": { "type": "string" },
        "tag": { "type": "string" }
      }
    }
  }
}
```

Lint and test before release:
```bash
helm lint ./mychart
helm template mychart ./mychart --values ci-values.yaml | kubectl apply --dry-run=client -f -
helm test mychart-release
```

## Gotchas
- Never hardcode namespace in templates; use `{{ .Release.Namespace }}`
- `helm upgrade --atomic` rolls back on failure but leaves the old release active — test rollback time
- Sub-chart values must be nested under the sub-chart name key in parent `values.yaml`
- `helm secret` plugin is needed to encrypt secrets at rest in Git; never use raw `Secret` manifests with base64 values committed
- Bump `version` in `Chart.yaml` on every change; `appVersion` tracks the app image version

## Related
- `helm-values-override-strategy.md`
- `kustomize-vs-helm-2026.md`
- `k8s-helmfile-2026.md`
