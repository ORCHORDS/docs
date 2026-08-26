# Platform Engineering and Internal Developer Platforms

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Every product team writes its own Terraform modules, Dockerfile
templates, and deployment scripts. Onboarding a new engineer to
get their first PR deployed takes three days and a Notion doc
nobody keeps current. A security audit finds eight different
approaches to secrets management across twelve services. The
infrastructure team is a bottleneck: every team files tickets
and waits. Senior engineers spend 30% of their time helping
juniors set up environments instead of building product.

## Context

Platform engineering treats internal infrastructure capabilities
as a product, delivered to developer teams (the customers) via
a self-service Internal Developer Platform (IDP). The IDP is
not a portal or a wiki — it is a paved road: a curated set of
golden paths that make the right way the easy way. The platform
team owns the road; product teams drive on it. Gartner predicted
that by 2026, 80% of large software engineering organizations
would establish platform engineering teams. The discipline emerged
from the insight that DevOps "you build it, you run it" created
cognitive overload — developers cannot be experts in both product
and infrastructure. The IDP abstracts infrastructure complexity
without hiding control.

## What an IDP is and is not

```
An IDP provides:
  → Self-service workflows for common operations
    (create service, deploy to staging, provision database)
  → Golden paths: opinionated, supported starting points
    for new services (templates, Cookiecutter, Backstage)
  → Infrastructure abstractions (not raw cloud APIs)
  → Developer portals for discoverability (Backstage.io)
  → Guardrails baked in: security, compliance, cost limits

An IDP is NOT:
  → A wiki of documentation
  → A ticketing system for infra requests
  → A committee approval process in a UI
  → A replacement for SRE on-call
  → An excuse to mandate one tool for every team
```

## Golden paths

```
A golden path is the recommended, supported way to accomplish
a common task. It is golden because:
  1. It is well-maintained and battle-tested in production
  2. It includes security, monitoring, and cost defaults
  3. It is documented with runbooks and escalation paths
  4. The platform team commits to keeping it working

Golden path components:
  Service templates:    Cookiecutter / Backstage scaffolder
  CI/CD pipelines:      Reusable GitHub Actions workflows
  IaC modules:          Curated Terraform/Pulumi modules
  Secrets management:   Single approved pattern (Vault, AWS SM)
  Observability:        Auto-instrumented OTel sidecars
  Deployment:           Argo CD ApplicationSet templates

Teams can leave the path. The platform team does not
prevent it. But off-path teams own their own maintenance.
```

## Backstage.io as a developer portal

```
Backstage (CNCF, originally Spotify) provides:
  → Software catalog: inventory of all services, owners,
    health status, docs, runbooks in one place
  → Scaffolder: templates to create new services on the
    golden path from a UI (wizard → PR in minutes)
  → TechDocs: docs-as-code rendered inside Backstage
  → Plugins: CI status, cost, security findings, on-call
    schedule — all surfaced next to the service entry

Adoption reality:
  Backstage works well when the catalog is kept accurate.
  Stale catalog entries erode trust faster than no catalog.
  Require teams to register services at creation time via
  the Scaffolder — do not ask them to add entries manually
  after the fact.
```

## Product mindset for platform teams

```
Treat the IDP as a product, not a shared service:
  → Developers are customers. Measure their satisfaction.
  → Define SLOs for the platform (golden path onboarding
    time, self-service success rate, portal uptime).
  → Run quarterly developer experience surveys targeting
    platform capabilities specifically.
  → Maintain a product roadmap; communicate it.
  → Deprecate features that nobody uses.

Platform team metrics:
  DORA metrics for platform itself (deploy frequency,
  change failure rate of platform changes).
  Adoption rate: % of new services using golden path.
  Self-service ratio: % of infra changes via IDP vs tickets.
  Time-to-first-deploy for new engineers.
  Developer satisfaction score (quarterly NPS or survey).
```

## When NOT to build an IDP

```
Do not build an IDP if:
  → Fewer than 30 engineers: the overhead exceeds the value.
    Use a shared conventions doc and a single CI template.
  → No dedicated platform team: an IDP built as a side
    project by product engineers becomes abandoned ware.
    Staff it before building it.
  → Developer pain is not bottleneck: if the team ships
    fast and satisfaction is high, an IDP adds complexity
    with no payoff.
  → You are trying to enforce compliance via the UI:
    compliance gates belong in policy-as-code (OPA/Kyverno),
    not in a portal that engineers learn to route around.

Right time to start:
  → 30-100 engineers: lightweight golden paths only
    (shared Terraform modules, reusable CI workflows).
  → 100+ engineers: dedicated platform team justified;
    Backstage catalog provides real value at this scale.
  → Multiple teams reinventing the same infrastructure:
    clear signal that path paving has positive ROI.
```

## Anti-patterns

- **Building a portal before building the golden path** —
  Backstage with nothing behind it is a fancy Notion page.
  Build the paths first; add the portal when teams would
  benefit from discoverability.
- **Forced migration, no escape hatch** — mandating that
  all existing services migrate to the golden path by a
  deadline creates resentment and rushed migrations.
  Provide the path; let teams adopt at their pace.
- **Platform team as gatekeeper** — if teams still open
  tickets for every infrastructure action, the IDP has
  failed its purpose. Self-service is the goal.
- **Ignoring developer feedback** — building features
  product teams did not ask for while ignoring friction
  they report weekly. Run regular office hours and
  quarterly surveys to prioritize the roadmap.

## Gotchas

- **Backstage catalog rot** — catalog entries go stale
  if there is no enforcement mechanism. Automate catalog
  registration via Scaffolder and add health checks that
  alert on stale or orphaned entries.
- **Golden paths can slow elite teams** — senior engineers
  on greenfield projects may be slowed by opinionated
  templates. Make the path the default, not the only option.
- **Platform team burnout** — platform teams that are
  on-call for every team's infrastructure issues without
  clear ownership boundaries burn out quickly. Define what
  the platform team owns vs what product teams own.
- **IDP sprawl** — building too many golden paths for
  every possible technology stack. Maintain three to five
  paths well rather than ten paths poorly.

## Verification

- New service creation follows the golden path via Scaffolder
  with no manual steps outside the workflow.
- Backstage catalog covers all production services with
  accurate owners, runbooks, and dependency links.
- Self-service ratio (IDP vs ticket-based changes) reviewed
  quarterly and trending upward.
- Developer satisfaction survey run quarterly, results
  shared publicly with the platform roadmap.

## Related

- `documentation/docs/policies/lessons/dora-metrics-engineering-measurement.md`
- `documentation/docs/policies/lessons/technical-debt-measurement-prioritization.md`
- `documentation/docs/policies/lessons/documentation-decays-without-ownership.md`
- `documentation/docs/policies/lessons/feature-flags-before-code-changes.md`

## Source URLs (verified 2026-08-17)

- Backstage.io documentation — https://backstage.io/docs/overview/what-is-backstage
- Platform Engineering on Kubernetes (CNCF report) — https://www.cncf.io/reports/platform-engineering/
- Internal Developer Platform Guide — https://internaldeveloperplatform.org/what-is-an-internal-developer-platform/
- Gartner Platform Engineering 2026 prediction — https://www.gartner.com/en/articles/what-is-platform-engineering
- Team Topologies — platform team patterns — https://teamtopologies.com/key-concepts
