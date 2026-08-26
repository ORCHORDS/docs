# golden-path-templates

**Issue:** Creating opinionated service templates that encode platform best practices by default
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
New services missing structured logging, health checks, metrics, or CI pipelines. Each team reinvents the same boilerplate differently. Standards drift over time.

## Pattern / Solution
Backstage software template:
```yaml
# template.yaml
apiVersion: scaffolder.backstage.io/v1beta3
kind: Template
metadata:
  name: nodejs-service
  title: Node.js Microservice
  description: Production-ready Node.js service with observability, CI/CD
spec:
  owner: platform-team
  type: service
  parameters:
    - title: Service Details
      properties:
        name:
          title: Service name
          type: string
          pattern: '^[a-z][a-z0-9-]{2,30}$'
        owner:
          title: Team
          type: string
          ui:field: OwnerPicker
        port:
          title: HTTP port
          type: integer
          default: 3000

  steps:
    - id: fetch-template
      name: Fetch template
      action: fetch:template
      input:
        url: ./skeleton
        values:
          name: ${{ parameters.name }}
          owner: ${{ parameters.owner }}
          port: ${{ parameters.port }}

    - id: create-repo
      name: Create GitHub repo
      action: github:repo:create
      input:
        repoUrl: github.com?owner=acme-corp&repo=${{ parameters.name }}

    - id: push-code
      name: Push template code
      action: github:repo:push

    - id: register-catalog
      name: Register in catalog
      action: catalog:register
      input:
        repoContentsUrl: ${{ steps['create-repo'].output.repoContentsUrl }}
        catalogInfoPath: '/catalog-info.yaml'
```

What every template skeleton includes:
```
skeleton/
├── .github/workflows/ci.yml        # lint, test, build, push image
├── Dockerfile                       # multi-stage, non-root user
├── catalog-info.yaml               # Backstage registration
├── mkdocs.yml + docs/              # TechDocs
├── src/
│   ├── index.ts                    # server with graceful shutdown
│   ├── health.ts                   # /health and /ready endpoints
│   └── metrics.ts                  # Prometheus metrics endpoint
├── helm/                           # Helm chart with HPA, PDB, resource limits
└── .envrc                          # direnv for local secrets
```

## Gotchas
- Templates drift from production reality without maintenance — assign an owner to each template
- Use `required` parameters and validation to prevent misconfigured services at creation time
- Templates should apply over time — use Renovate/Dependabot to keep generated repos up to date
- Don't over-constrain — golden path should be the easiest path, not the only path

## Related
- `developer-portal-backstage.md`
- `platform-engineering-idp.md`
- `iac-best-practices.md`
