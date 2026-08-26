# Build vs Buy Decisions for Cloudflare-Adjacent Tooling

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You are running a startup-scale product on Cloudflare Workers, Pages, D1, and R2.
Every week a new SaaS tool arrives in your team's Slack with a proposal to solve
something: email delivery, cron scheduling, full-text search, queue management, PDF
generation, analytics, feature flags, audit logs. The build-vs-buy question comes up
constantly, and without a framework for answering it, you will either over-spend on
SaaS subscriptions or over-invest in bespoke infrastructure that steals engineering
time from the product.

This article gives a decision framework calibrated for Cloudflare-native stacks and
small (2–10 engineer) teams.

---

## Context

The Cloudflare ecosystem has shifted the build-vs-buy calculus compared to 2020.
Several capabilities that previously required a managed SaaS are now available as
native primitives:

| Capability | Previously | Now (Cloudflare native) |
|---|---|---|
| Caching | Redis / Memcached | Workers Cache API, KV |
| Simple queues | SQS, RabbitMQ | Cloudflare Queues |
| Scheduled jobs | Heroku Scheduler, AWS EventBridge | Workers Cron Triggers |
| Object storage | S3 + CloudFront | R2 + Workers |
| Relational DB | PlanetScale, Neon, Supabase | D1 (SQLite at the edge) |
| Rate limiting | Custom middleware or Nginx | Workers Rate Limiting (native) |
| A/B testing infra | LaunchDarkly, Statsig | Workers + KV (buildable) |

This does not mean "always build." It means the bar for "just use the SaaS" is now
higher because the infrastructure cost of building is lower.

---

## Section 1 — The Decision Framework

Use five criteria. Score each 1–3. If the total is ≥ 10, lean build. Below 8, lean
buy. 8–9, evaluate the maintenance burden explicitly.

**Criterion 1 — Strategic core (1–3)**
Is this capability directly related to your product's differentiation?
- 1: Commodity utility (email delivery, PDF generation)
- 2: Adjacent (analytics, feature flags, search)
- 3: Core product surface (your own domain logic)

Strategic core capabilities are worth building. Commodity utilities are not.

**Criterion 2 — Cloudflare native fit (1–3)**
Does a Cloudflare primitive cover 80 % of the requirement?
- 1: Requires external service regardless (e.g., transactional email)
- 2: Cloudflare covers the runtime but you still need an external data store
- 3: Fully expressible as Workers + KV / D1 / Queues / R2

**Criterion 3 — Team capacity (1–3)**
What is the ongoing maintenance cost?
- 1: High — requires dedicated attention (custom search engine, payment processing)
- 2: Medium — a weekly hour of ops
- 3: Low — deploy-once, monitor-only

**Criterion 4 — Vendor lock-in risk (1–3)**
If you buy, how hard is switching?
- 1: Standard protocol, portable data (SMTP for email, S3-compatible for storage)
- 2: Proprietary SDK but data is exportable
- 3: Deep integration, hard to eject

Note: This criterion is inverted — high lock-in risk pushes toward build, not buy.
Score 3 if lock-in is low (easy to switch), 1 if lock-in is high.

**Criterion 5 — Operational risk of self-hosting (1–3)**
If you build, what breaks if it goes wrong?
- 1: Low blast radius (internal tooling)
- 2: Degrades customer experience
- 3: Data loss or compliance exposure

---

## Section 2 — Decisions by Category

**Transactional email** → **Buy**
Every team that has tried to build their own email delivery stack has regretted it.
Deliverability is a specialisation requiring active IP reputation management,
DMARC/DKIM/SPF configuration, bounce handling, and feedback loop processing.
Use Resend, SendGrid, or Postmark. The Workers integration is a `fetch()` to their
API. This is a commodity utility with high operational risk and low Cloudflare native
fit.

**Full-text search** → **Buy (until you hit pricing pain)**
Cloudflare does not have a native full-text search primitive. Your options:
- Cloudflare Vectorize (vector similarity, not keyword)
- Algolia / Typesense / Meilisearch (SaaS or self-hosted)
- D1 FTS (SQLite's built-in FTS5, available in D1, limited)

For <10k searchable documents, D1 FTS5 is worth evaluating before paying for Algolia.
For larger corpora or faceted search, buy Algolia or host Meilisearch on a VPS.

**Feature flags** → **Build (for simple cases), Buy (for experimentation)**
Simple on/off flags for a 2-engineer team: a KV namespace with JSON values and a
helper function is a 2-hour build. You own the data, you own the latency (KV edge
reads are ~1 ms), you own the schema.

Experimentation (A/B with statistical significance, targeting rules, percentage
rollouts across user segments): buy LaunchDarkly or Statsig. Experimentation math is
subtle, and building it correctly takes weeks.

The rule: if it is a kill switch or a preview flag, build it. If it is an experiment
with a hypothesis and a p-value, buy it.

**PDF generation** → **Buy**
PDF generation from HTML is a browser-rendering problem. Workers do not have a
headless browser. Options are: Puppeteer on a VPS, a SaaS (Browserless, PDFShift,
DocRaptor), or a client-side library (jsPDF, pdfmake in the browser). Do not spend
engineering time on this unless PDF quality is a product differentiator.

**Analytics / event tracking** → **Split**
Page-view and click analytics: use Cloudflare Web Analytics (free, no cookies, built
into the dashboard). Do not add a third JS tag for this.

Product analytics (funnels, cohort analysis, retention): buy PostHog (open source,
self-host on a VPS or use their cloud). Product analytics require the kind of query
flexibility (SQL-based funnel builder) that is not worth building.

**Queue / async job processing** → **Build on Cloudflare Queues**
Cloudflare Queues (GA 2024) handles at-least-once delivery, dead-letter queues, batch
consumption, and retry with backoff. For a Workers-native stack, this covers 90 % of
async job needs. There is no operational overhead — it is a binding in `wrangler.toml`.

Buy SQS or RabbitMQ only if you need: ordered delivery with strict guarantees beyond
what Queues offers, or cross-cloud fan-out (Queues is Cloudflare-only).

**Cron scheduling** → **Build with Workers Cron Triggers**
Workers Cron Triggers support standard cron syntax, fire a Worker on schedule, and
are configured in `wrangler.toml`. For a Cloudflare-native stack, this is a zero-
operational-overhead build. The only limitation: cron jobs run for at most 15 minutes
(CPU time, not wall time). For longer-running jobs, chain through Queues.

**Rate limiting** → **Build with Workers Rate Limiting API**
Cloudflare's native Rate Limiting is now available as a Workers binding. It handles
distributed counting across the Cloudflare network — something that is very hard to
build correctly on your own. Use the binding. It is not worth buying a third-party
rate-limiting service when this is native.

**Observability (logs, traces, errors)** → **Buy**
Do not build your own log aggregation, distributed tracing, or error tracking. Use
Sentry for errors, Axiom or Datadog for structured logs (via Logpush), and Honeycomb
or Grafana Tempo for tracing. The operational cost of maintaining these systems at
startup scale is unjustifiable.

---

## Section 3 — The "Not Now" Category

Some tools are "not now" rather than "build or buy." When the team is under 5
engineers, resist the pull toward:

- **Audit log SaaS (WorkOS, Panther)**: a D1 table with an append-only insert is
  sufficient until you have enterprise customers who need audit log export.
- **Feature flag SaaS for simple flags**: covered in Section 2.
- **Internal developer portals (Backstage, Port)**: relevant when you have >10 teams.
  Before that, a README and a CODEOWNERS file are your developer portal.
- **Data warehouse (Snowflake, BigQuery)**: Workers Analytics Engine exports to R2.
  Query it with DuckDB locally or with a lightweight BI tool. A data warehouse is a
  2026 problem if you are a 2026 startup.

---

## Anti-patterns

- **Building to avoid vendor dependency and then not maintaining what you built.**
  A self-built system that is never updated accumulates security debt faster than a
  vendor who patches for you.
- **Buying every tool a team member used at their last big-tech employer.** Enterprise
  tooling is priced for enterprise budgets. Datadog at $500/month is not the same
  value proposition for a 3-engineer startup as it is for a 300-engineer company.
- **Assuming "it is open source so we can just self-host it" is free.** Self-hosting
  Meilisearch, Metabase, or Plausible requires a VPS, backups, upgrades, and someone's
  attention on-call. Staff cost > SaaS cost at small scale.
- **Deciding once and not revisiting.** Build-vs-buy decisions expire. A SaaS that
  cost $50/month at 1,000 users may cost $5,000/month at 100,000 users. Put a review
  date on build-vs-buy decisions (use ADRs for this).
- **Choosing build to "learn the technology" rather than to serve the customer.**
  Building a queue system to learn about distributed systems is a valid learning
  exercise. It is not a valid product decision.

---

## Gotchas

- **Cloudflare's free tier is generous but has hard limits.** Workers: 100k requests/
  day free. D1: 5 GB free. R2: 10 GB free. KV: 100k reads/day free. Build tooling
  budget assumptions around the paid tiers, not the free tier.
- **"We will migrate to the Cloudflare native version later" is technical debt.**
  If you are buying a SaaS to bridge a gap, set a concrete trigger (user count, cost
  threshold, or date) for re-evaluating the build path. Otherwise "later" never comes.
- **Workers have no persistent connections.** You cannot hold a WebSocket to a Redis
  instance across requests. Design patterns that assume persistent connection pools
  (Prisma + PostgreSQL connection pool, Bull with Redis) need re-architecture before
  they work in Workers.
- **Vendor contracts have data residency implications.** If your product handles EU
  personal data, verify that the SaaS you are buying can satisfy GDPR data residency
  requirements before signing. Cloudflare's Smart Placement and regional hints give
  you control; some SaaS tools do not.

---

## Verification

After making a build-vs-buy decision, document it as an ADR (see
`architecture-decision-records-adr-workflow.md`) with:

- The five-criterion scores and their rationale
- The alternatives considered
- The review trigger (date, cost threshold, or user volume)
- The owner responsible for re-evaluating

Revisit all active build-vs-buy ADRs in the quarterly engineering review.

---

## Related

- `architecture-decision-records-adr-workflow.md`
- `boring-technology-wins-long-term.md`
- `over-engineering-is-a-form-of-tech-debt.md`
- `developer-experience-dx-cloudflare-workers.md`
- `feature-flag-lifecycle-management.md`
- `scope-discipline.md`

---

## Sources

- Cloudflare Queues documentation: https://developers.cloudflare.com/queues/
- Cloudflare Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Cloudflare Rate Limiting API: https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/
- "Build vs Buy" — a16z Engineering: https://a16z.com/build-vs-buy/
- Cloudflare Workers Limits: https://developers.cloudflare.com/workers/platform/limits/
