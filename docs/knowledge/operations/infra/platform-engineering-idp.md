# platform-engineering-idp

**Issue:** Building an Internal Developer Platform (IDP) to reduce cognitive load and increase developer velocity
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Developers spend hours waiting for infrastructure provisioning, debugging deployment pipelines, and learning cloud-specific tooling. Platform knowledge siloed in SRE team. Onboarding takes weeks.

## Pattern / Solution
IDP capability model (Gartner):
```
Layer 5 — Developer Experience: portal, CLI, docs
Layer 4 — Application Services: templates, pipelines, observability
Layer 3 — Orchestration: K8s, service mesh, secrets management
Layer 2 — Compute: cloud providers, bare metal
Layer 1 — Infra provisioning: Terraform, Crossplane
```

Core IDP components:
```
Self-service portal (Backstage):
  - Service catalog: discover all services and their owners
  - Software templates: scaffold new services with golden path
  - Tech docs: docs-as-code auto-published from repos
  - Plugins: PagerDuty, Grafana, GitHub, cost data

Deployment platform:
  - PR → build → test → stage → prod pipeline (opinionated)
  - Environment promotion gates (tests pass, SLO green)
  - Self-service env creation for feature branches

Observability defaults:
  - Every new service gets: metrics, logs, traces, dashboards, alerts
  - Auto-linked from service catalog entry
  - No configuration required from the app developer

Secrets management:
  - `vault kv put secret/my-service/prod KEY=value`
  - Auto-injected as env vars at deploy time
```

Platform team metrics (measure IDP value):
```
DORA metrics:
  Deployment frequency: target > 1/day per service
  Lead time for changes: code commit → prod < 1 hour
  Change failure rate: < 5%
  MTTR: < 1 hour

Developer satisfaction (quarterly survey):
  "How easy was it to deploy your last change?" (1–5)
  "How long did you wait for infrastructure?" (hours)
```

## Gotchas
- IDP is a product — needs a product manager, roadmap, and user research
- Don't build everything custom — use Backstage, Port, or Cortex rather than wiki-based portal
- Golden paths must be maintained — stale templates are worse than none
- Platform team must avoid becoming a bottleneck — self-service is the goal, not approval workflows

## Related
- `developer-portal-backstage.md`
- `golden-path-templates.md`
- `toil-reduction-sre.md`
