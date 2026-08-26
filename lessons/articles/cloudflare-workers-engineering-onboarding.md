# Engineering Onboarding for Cloudflare Workers Teams

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A new engineer joins the team. They spend their first week in Zoom calls trying
to understand which Worker handles which domain, why there are three different
KV namespaces with similar names, and what `wrangler deploy --env staging`
actually does. By day ten they push a change that silently overwrites the wrong
binding because no one told them the environment variable naming convention.
They're productive by week six — not week one.

Good onboarding for a Cloudflare Workers team cuts that ramp to 1–2 weeks and
produces engineers who understand the system boundaries, can deploy safely, and
can follow the on-call runbook without shadowing someone.

## Context

Cloudflare Workers present unusual onboarding challenges that differ from
traditional backend or frontend onboarding:

- **No traditional server mental model** — Workers run at the edge, not in a
  region. CPU time limits (50ms on the free plan, effectively unbounded on
  Workers Paid but still per-request) mean long-running patterns don't apply.
- **Many primitives, non-obvious composition** — KV, R2, D1, Durable Objects,
  Queues, Analytics Engine, Hyperdrive, and Service Bindings all behave
  differently from each other and from their Node.js equivalents.
- **wrangler.toml is infrastructure-as-code** — Changes to `wrangler.toml`
  deploy live infrastructure. New engineers need to understand this before they
  touch it.
- **Local dev is imperfect** — Miniflare and `wrangler dev --remote` bridge the
  gap but the parity is not 1:1. Durable Objects especially have edge-only
  behaviour that surprises new engineers.

This article defines a structured 30-day onboarding track covering environment
setup, primitive fluency, deploy safety, and on-call readiness.

---

## Week 1 — Environment, Access, and Reading Code

### Access checklist

Before a new engineer writes a single line of code, they need access. Do not
make them hunt for this.

```markdown
## Onboarding Access Checklist

### Day 1 — Immediate
- [ ] Cloudflare account added to org with Member role (not Admin yet)
- [ ] Invited to team's wrangler.toml-managed environments in CF dashboard
- [ ] GitHub repo access granted (specific repos, not org-wide)
- [ ] PagerDuty account created, added to shadow rotation
- [ ] Slack: #incidents, #deploys, #platform-eng, #workers-team
- [ ] Linear/Jira project access
- [ ] 1Password vault access for shared secrets

### Day 2 — Development environment
- [ ] Node.js (LTS) installed via nvm or fnm
- [ ] wrangler CLI installed globally: npm install -g wrangler
- [ ] wrangler login run and verified: wrangler whoami
- [ ] Repo cloned and `npm install` succeeds
- [ ] `wrangler dev` runs against staging environment
- [ ] First `wrangler tail --env staging` works (can see live logs)

### Day 3 — Verify environment parity
- [ ] Can access staging dashboard at CF console
- [ ] Understands which KV namespaces are staging vs production
- [ ] Has read the wrangler.toml for each Worker they will touch
- [ ] Has read the binding naming convention doc
```

### The wrangler.toml literacy session

Run a 45-minute pairing session on day 2 or 3. Cover:

```toml
# Example annotated wrangler.toml for a new engineer reading session

name = "api-worker"                  # This is the Worker name in the CF dashboard.
                                     # Changing this creates a NEW Worker, does not
                                     # rename the existing one. Data loss risk!

main = "src/index.ts"
compatibility_date = "2024-09-23"    # Pin this. Advancing it can change runtime
                                     # behaviour. Always check the compat flag
                                     # changelog before bumping.

[env.staging]
name = "api-worker-staging"          # Staging Worker has its own name.

[[env.staging.kv_namespaces]]
binding = "SESSIONS"                 # This is the variable name in your Worker code.
id = "abc123..."                     # This is the staging namespace ID.
                                     # It is NOT the production namespace.

[env.production]
name = "api-worker"

[[env.production.kv_namespaces]]
binding = "SESSIONS"                 # Same binding name, different ID.
id = "xyz789..."                     # Production namespace. Writes here are live.

# Key lesson: `wrangler deploy` with no --env flag deploys to production
# by default if production is the default env. ALWAYS specify --env.
```

The key rule to drive home: **`wrangler deploy` without `--env staging` can go
to production.** Add a Makefile target to enforce this:

```makefile
# Makefile
.PHONY: deploy-staging deploy-production

deploy-staging:
    wrangler deploy --env staging

deploy-production:
    @echo "Deploying to PRODUCTION. Are you sure? [y/N]" && \
    read ans && [ $${ans:-N} = y ] && \
    wrangler deploy --env production
```

---

## Week 2 — Primitive Fluency

### KV, R2, and D1: the three storage primitives

New engineers routinely pick the wrong primitive. This decision table prevents
that conversation from happening at code review time:

```
Storage Primitive Decision Table
---------------------------------
Use KV when:
  - Data is read frequently, written rarely
  - Eventual consistency (seconds) is acceptable
  - Value size <= 25 MB
  - You need global low-latency reads
  Example: feature flags, user settings, rate limit state

Use R2 when:
  - Storing blobs, files, media
  - Need S3-compatible API
  - No egress cost matters
  Example: user uploads, build artefacts, static assets

Use D1 when:
  - Relational data with SQL queries
  - Transactional writes matter
  - Data is not purely edge-cached reads
  Example: user profiles, orders, content tables

Use Durable Objects when:
  - You need strongly consistent state per entity
  - WebSocket connections or coordination between requests
  - Rate limiting at per-user granularity
  Example: collaborative editing, presence, per-user rate limiter

Use Queues when:
  - Decoupling a slow async task from the request path
  - Fan-out from one event to many consumers
  Example: sending emails, processing uploads, webhooks
```

Assign a day-2 week-2 exercise: write a Worker that uses KV for caching and
D1 for persistent data. Review the code together and talk through why each
primitive was chosen.

### Service Bindings exercise

Service Bindings are the most confusing primitive for engineers coming from
HTTP microservices. They communicate between Workers without going through
the public internet — zero latency, same-request lifecycle.

```typescript
// worker-a/src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Calling Worker B via service binding — NOT an HTTP call over the network.
    // This executes in the same isolate group on the same edge node.
    const result = await env.WORKER_B.fetch(
      new Request('https://worker-b/internal/compute', {
        method: 'POST',
        body: JSON.stringify({ input: 'data' }),
      })
    );
    return result;
  }
};

interface Env {
  WORKER_B: Fetcher; // The binding type for service bindings
}
```

```toml
# worker-a/wrangler.toml
[[services]]
binding = "WORKER_B"
service = "worker-b"          # The name field of the target Worker
environment = "staging"       # Pin to the same environment!
```

Common mistake: forgetting `environment` means staging Worker A calls
production Worker B. Add a lint check or CI assertion.

---

## Week 3 — Deploy Safety and Observability

### Gradual rollout with `wrangler versions`

Workers Gradual Deployments (split traffic) should be the standard deploy path
for anything touching the critical path.

```bash
# Upload a new version without sending traffic to it
wrangler versions upload --env production

# List versions and their traffic weights
wrangler versions list --env production

# Split: 10% to new version, 90% to previous
wrangler deployments create \
  --version-id <new-version-id> --percentage 10 \
  --version-id <old-version-id> --percentage 90 \
  --env production

# Promote to 100% once metrics look healthy
wrangler deployments create \
  --version-id <new-version-id> --percentage 100 \
  --env production
```

Teach new engineers to instrument their Workers before promoting:

```typescript
// Every Worker should emit these baseline metrics
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const start = Date.now();
    let status = 200;

    try {
      const response = await handle(request, env, ctx);
      status = response.status;
      return response;
    } catch (err) {
      status = 500;
      throw err;
    } finally {
      // Workers Analytics Engine for custom metrics
      env.ANALYTICS.writeDataPoint({
        blobs: [request.url, request.method, String(status)],
        doubles: [Date.now() - start],
        indexes: [new URL(request.url).pathname],
      });
    }
  }
};
```

### Reading logs with `wrangler tail`

```bash
# Real-time log tail for a specific environment
wrangler tail api-worker --env staging

# Filter to errors only
wrangler tail api-worker --env production --status error

# Search for a specific pattern (grep the output)
wrangler tail api-worker --env production | grep "USER_ID=abc123"

# JSON format for structured log parsing
wrangler tail api-worker --env production --format json | jq '.logs[].message'
```

---

## Week 4 — On-call Readiness

### Runbook dry run

Before the new engineer enters the on-call rotation (even in shadow mode),
they must complete a runbook dry run. Have them follow the on-call runbook
for your top 3 alert types on staging:

1. "High error rate on api-worker" — walk through the triage steps.
2. "D1 query p99 > 500ms" — find the slow query in Analytics Engine.
3. "KV write errors > 0.1%" — identify which namespace and what the retry
   policy does.

Validate they can execute each step independently without asking for help.

### 30-60-90 day milestones

```markdown
## Onboarding Milestones

### Day 30
- [ ] Has deployed at least one change to staging independently
- [ ] Has deployed at least one change to production (with buddy review)
- [ ] Can read wrangler.toml for any team Worker and explain its bindings
- [ ] Has shadowed at least one real incident
- [ ] Has completed the runbook dry run

### Day 60
- [ ] Has owned a full feature from dev to production deploy
- [ ] Is in the on-call rotation (with buddy escalation)
- [ ] Has written or updated at least one runbook entry
- [ ] Has participated in a post-mortem

### Day 90
- [ ] Can independently triage any P1 alert in the team's domain
- [ ] Has mentored a day-30 engineer through their first deploy
- [ ] Has made at least one improvement to the onboarding doc
```

---

## Anti-patterns

- **Org-wide Admin access on day 1** — New engineers with Admin access to the
  CF account can delete Workers, KV namespaces, and R2 buckets. Member role
  is sufficient for the first 90 days.

- **Undocumented binding naming conventions** — If KV namespaces are named
  `CACHE_V1`, `CACHE_PROD`, and `KV_SESSIONS_STAGING`, a new engineer will
  misidentify them. Name everything `<SERVICE>_<PRIMITIVE>_<ENV>` or
  equivalent — and write it down.

- **"Just read the code"** — Workers codebases often lack a top-level README.
  New engineers spend days understanding request routing and environment
  configuration that should be a 20-minute document.

- **Skipping Miniflare limitations** — New engineers who don't know that
  Miniflare doesn't simulate real Durable Object geography will write code
  that works locally and fails at the edge.

- **Buddy overload** — Assigning one senior engineer as the single point of
  contact for a new hire creates a bottleneck. The buddy handles culture and
  priority questions; a structured document handles the technical checklist.

---

## Gotchas

- **`wrangler dev` uses local KV by default** — Writes during local dev go
  nowhere near staging data. Add `--remote` if you need to test against real
  staging KV. New engineers sometimes expect their local writes to persist.

- **Durable Objects need a migration block** — First-time DO deployment
  requires the `[[migrations]]` block in wrangler.toml. Skipping it produces
  a confusing error about missing classes. Include this in the annotated
  wrangler.toml in the onboarding docs.

- **CF dashboard account vs zone level** — Some settings are at the account
  level (Workers, KV namespaces) and some are at the zone level (DNS, Page
  Rules, Cache Rules). New engineers conflate them. The onboarding tour should
  explicitly show both levels in the dashboard.

- **Tail Workers are separate deployments** — Observability Workers that
  process tail events are their own named Workers and must be deployed
  separately. They look like an afterthought but go down if not included in
  the deploy pipeline.

---

## Verification

After each new engineer completes their 30-day milestone, run this checklist:

```
30-Day Onboarding Audit
------------------------
[ ] Engineer received all access items on day 1 (check access checklist doc)
[ ] Engineer completed wrangler.toml literacy session with a buddy
[ ] Engineer can answer: "What does --env do and when do I skip it?"
[ ] Engineer has done at least one staging deploy independently
[ ] Engineer passed the runbook dry run on all three alert scenarios
[ ] Engineer has the PagerDuty shadow rotation configured
[ ] Onboarding doc was updated with at least one improvement by this engineer
```

If any item is not checked, the *process* failed, not the engineer.
Update the onboarding doc accordingly.

---

## Related

- `developer-experience-dx-cloudflare-workers.md`
- `zero-downtime-deployment-workers.md`
- `workers-testing-miniflare-vitest.md`
- `cloudflare-storage-primitive-selection.md`
- `cost-optimization-cloudflare-stack.md`
- `write-the-runbook-before-the-incident.md`
- `on-call-rotation-design-runbooks.md`

## Sources

- Cloudflare Workers documentation — developers.cloudflare.com/workers/
- Cloudflare Durable Objects docs — developers.cloudflare.com/durable-objects/
- Wrangler CLI reference — developers.cloudflare.com/workers/wrangler/
- Cloudflare Workers Gradual Deployments — developers.cloudflare.com/workers/configuration/versions-and-deployments/
- Google SRE Book, Ch. 28 "Accelerating SREs to On-Call and Beyond"
- Stripe Engineering, "How we think about onboarding" (internal adaptation)
