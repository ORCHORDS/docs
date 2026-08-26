# helm-values-override-strategy

**Issue:** Managing per-environment Helm values without duplicating configuration
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams end up with massive per-env values files that diverge silently. A layered override strategy keeps defaults DRY while allowing environment-specific tuning.

## Pattern / Solution
Layer order (later files win):
```
values.yaml          # chart defaults — must compile on its own
values-common.yaml   # org-wide overrides (image pull secrets, resource floors)
values-staging.yaml  # staging-specific (smaller replicas, debug flags)
values-prod.yaml     # production (HA, larger limits, real secrets refs)
```

Helm install with layers:
```bash
helm upgrade --install myapp ./mychart \
  -f values.yaml \
  -f values-common.yaml \
  -f "values-${ENV}.yaml" \
  --set image.tag="${GIT_SHA}" \
  --set global.deployTime="$(date -u +%s)"
```

Helmfile for declarative layering:
```yaml
# helmfile.yaml
releases:
  - name: myapp
    chart: ./mychart
    values:
      - values.yaml
      - values-common.yaml
      - values-{{ .Environment.Name }}.yaml
    set:
      - name: image.tag
        value: {{ requiredEnv "IMAGE_TAG" }}
environments:
  staging: {}
  production: {}
```

Run: `helmfile -e production apply`

Secret injection (never in values files):
```yaml
# Use external-secrets operator or vault-agent; reference in values:
existingSecret: myapp-db-credentials
```

## Gotchas
- `--set` always overrides `-f` values; use `--set` only for dynamic values (SHA, timestamp)
- YAML merge keys (`<<: *anchor`) do not work in Helm values — Helm deep-merges files instead
- Boolean values set via `--set` must be quoted: `--set feature.enabled=true` (no quotes) works, but `--set feature.enabled="true"` becomes a string
- Never store production replicas or resource limits only in CI `--set` flags; they disappear on rollback

## Related
- `helm-chart-best-practices.md`
- `k8s-helmfile-2026.md`
- `secrets-in-deploy-2026.md`
- `environment-promotion-gates.md`
