# developer-portal-backstage

**Issue:** Deploying and configuring Spotify Backstage as an internal developer portal
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
No single place for developers to discover services, runbooks, owners, or deployment status. Knowledge scattered across Confluence, Slack, and tribal memory.

## Pattern / Solution
Bootstrap Backstage:
```bash
npx @backstage/create-app@latest --skip-install
cd my-backstage && yarn install
```

Core configuration (`app-config.yaml`):
```yaml
app:
  title: Acme Developer Portal
  baseUrl: https://backstage.acme.internal

backend:
  baseUrl: https://backstage.acme.internal
  database:
    client: pg
    connection:
      host: ${POSTGRES_HOST}
      database: backstage

catalog:
  providers:
    github:
      acme-org:
        organization: 'acme-corp'
        catalogPath: '/catalog-info.yaml'
        filters:
          branch: 'main'
        schedule:
          frequency: { minutes: 30 }
          timeout: { minutes: 3 }

techdocs:
  builder: 'external'   # build docs in CI, store in S3
  publisher:
    type: 'awsS3'
    awsS3:
      bucketName: acme-techdocs
      region: us-east-1
```

Service catalog entry (`catalog-info.yaml` in each repo):
```yaml
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: orders-api
  description: Order management service
  tags: [nodejs, postgres, critical]
  links:
    - url: https://grafana.acme.internal/d/orders
      title: Dashboard
    - url: https://runbooks.acme.internal/orders
      title: Runbook
  annotations:
    github.com/project-slug: acme-corp/orders-api
    pagerduty.com/service-id: P123456
    backstage.io/techdocs-ref: dir:.
spec:
  type: service
  lifecycle: production
  owner: team-commerce
  system: order-management
  dependsOn:
    - component:payment-api
    - resource:orders-db
```

## Gotchas
- Backstage requires a PostgreSQL database — SQLite is dev-only and loses data on restart
- GitHub discovery scales to thousands of repos but needs a GitHub App (not PAT) for rate limits
- TechDocs auto-discovery requires `mkdocs.yml` at repo root with `docs_dir: docs/`
- Backstage plugins are React components — frontend and backend plugins are separate packages

## Related
- `platform-engineering-idp.md`
- `golden-path-templates.md`
- `iac-best-practices.md`
