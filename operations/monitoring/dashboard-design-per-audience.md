# dashboard-design-per-audience

**Issue:** The example project Grafana org has 200+ dashboards and none of them answer anyone's question in under 30 seconds. The single "overview" dashboard mixes p99 latency panels next to quarterly revenue counters; executives see noise they cannot act on, on-call engineers scroll past business metrics to find the error-rate panel they actually need at 3am, and support staff have no view at all so they ping engineering for every customer complaint. The fix is not more dashboards — it is designing a small number of dashboards per audience, each with an explicit owner, question, and altitude, linked together in a drill-down hierarchy.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The three canonical audiences and their views

1. **Executive / business view: service health as risk.** One screen, refreshed on long intervals: SLO attainment per product line, error-budget burn status (green/amber/red, not raw percentages), incident count and customer impact for the period, and one or two business KPIs like checkout conversion or active tenants. If a panel needs a legend explanation, it does not belong here.
2. **Engineer / on-call view: diagnose from symptom to cause.** Organized as a top row of golden signals (traffic, errors, latency, saturation) for the implicated service, followed by dependency panels and log/trace links scoped by dashboard variables. Every panel must be one click from a trace exemplar or log query — a dashboard that dead-ends forces the engineer back to ad-hoc query building during the incident.
3. **Support / ops view: is it us or is it them?** Per-tenant or per-region status panels, recent deploys and known incidents annotated on the timeline, and simple language ("Checkout degraded for EU tenants since 14:02"). This audience needs to answer customer tickets, not debug JVMs; give them the deploy/incident timeline overlay and nothing requiring query literacy.

## Structural rules that keep each dashboard honest

1. **One dashboard answers one recurring question.** Write the question in the dashboard description: "Am I burning error budget faster than 14.4x?" If two questions appear, split the dashboard. This rule alone prevents the 40-panel sprawl dashboard nobody trusts.
2. **Five panels above the fold, hard limit.** Research on dashboard mistakes consistently shows overload as failure mode number one: panels beyond the first screen are either redundant or stale. Deep detail lives in drill-down dashboards reached via data links, not additional rows.
3. **Use a hierarchy: global → service → resource.** Grafana's documented best practice is layered dashboards with drill-down links: a global health board links to per-service boards, which link to per-resource (host/worker/pod) boards. Each layer uses the same variable names (`service`, `env`, `region`) so links carry context down the chain.
4. **Default time ranges match audience cadence.** Executives get 30-day windows (SLO windows), on-call gets last 1h with 5m refresh, support gets last 24h. Never make anyone manually adjust the time picker to get their canonical view.
5. **Annotate deploys and incidents on every time series.** A latency spike without the deploy marker invites wrong hypotheses. This is also the cheapest cross-team alignment tool — see `deployment-event-tracking.md` for emitting the annotation events.

## Anti-patterns to delete on sight

1. **The wall of green.** A dashboard of 60 identical uptime panels trains eyes to skim, which means the one red tile gets noticed at minute 12 instead of minute 1. Replace with a single "top 5 worst SLO attainment" table plus an aggregate health stat.
2. **Averages without percentiles.** Executives do not need to know about averages, but engineers must never see p50 labeled as "latency" — p99 and error rate drive decisions, and averages hide the tail where users live. See `red-use-metrics-framework.md` for the metric selection.
3. **Dashboard-as-documentation.** A panel whose only purpose is "so we remember this metric exists" is a bookmark, not a dashboard. Metrics inventory belongs in the metrics catalog; dashboards exist to be looked at during decisions and incidents.
4. **Copy-paste service dashboards with hardcoded names.** Ten near-identical `checkout-api`, `search-api`, ... dashboards drift apart silently. Build one templated dashboard with a `service` variable and use variable-based links between layers.
5. **Owner-less dashboards.** Every dashboard gets a `owner` dashboard link or annotation naming a team channel. Quarterly, any dashboard with zero views (check usage analytics) and no owner gets archived — dashboard sprawl is a landfill problem, not a search problem.

## Rollout and governance for the fleet

1. **Start with three dashboards, not thirty.** Ship the exec health board, one on-call golden-signals template, and one support status view; iterate after two real incidents prove (or break) the drill-down paths. Retrofitting hierarchy onto 200 legacy dashboards never finishes — build the new spine and let old links rot until deleted.
2. **Manage dashboards as code.** Provision the canonical hierarchy from the repo (`monitoring-as-code.md`) so the structure survives Grafana org re-creation and changes are reviewed. Personal scratch dashboards live in a separate folder with auto-expiry.
3. **Instrument the dashboards themselves.** Grafana's dashboard usage analytics (or query-log analysis on the backend) tells you which panels are actually viewed. Design decisions made without view data are guesses; retire what nobody opens.
4. **Run the "stranger test" quarterly.** Someone outside the owning team gets 60 seconds with the exec dashboard and must correctly answer "is anything wrong right now, and for whom?" Failures drive the next revision — a dashboard that only its author can read is a private art project.
