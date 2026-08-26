# alert-quality-metrics-mtta-mttr

**Issue:** The team "feels" that alerting is noisy, tuning happens by anecdote after a bad night of pages, and nobody can say whether last quarter's alert-cleanup effort actually worked. Alert configuration techniques (grouping, inhibition, silencing) already exist in this KB — what is missing is measuring the alerting system itself. This article defines the metrics that quantify alert quality, how to instrument the alerting-to-incident pipeline to compute them, and the review cadence that turns them into steady improvement.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Core metrics to track

1. **MTTA (mean time to acknowledge).** The average time from page delivery to human acknowledgment; it is the primary alerting-health metric because it exposes routing problems, understaffed rotations, and alert fatigue long before they become missed incidents.
2. **MTTD and MTTR (mean time to detect/resolve).** Detection time measures how far behind reality your signals run, while resolution time measures the whole response including repair; tracking them separately tells you whether to invest in better monitoring or in faster remediation runbooks.
3. **Actionability rate (page-to-action ratio).** The fraction of pages that required a human to do something — anything — beyond acknowledging and closing them; the inverse is your false-positive rate, and it is the single best predictor of on-call burnout.
4. **Pages per shift and alert volume per rule.** Raw counts per on-call shift and per firing rule identify both workload hot spots and the specific rules generating most of the noise, turning "alerting is noisy" into a ranked worklist.
5. **Escalation rate.** The percentage of pages that escalate past the primary on-call before acknowledgment; sustained escalation means pages arrive to the wrong person, at the wrong time, or are being ignored — each with a different fix.

## Instrumenting the pipeline

1. **Export raw alert lifecycle events.** PagerDuty, OpsGenie, and Grafana OnCall all expose events (triggered, acknowledged, resolved, escalated) via API or webhooks; ship them to your warehouse or a metrics pipeline so quality is computed from source data, not manually tagged spreadsheets.
2. **Enrich every alert with owning metadata at route time.** Route-level labels (team, service, severity, runbook URL) must be stamped by the alerting config, not reconstructed later, because per-team dashboards and per-rule accountability are impossible if ownership has to be inferred after the fact.
3. **Define ack and resolve timestamps precisely.** Agree that MTTA starts at page delivery (not alert firing) and MTTR ends at resolution action (not auto-recovery), and automate both from the lifecycle events; hand-collected timestamps decay within weeks.
4. **Join alerts to incident records.** Whether in the incident tool or a simple table, recording which pages became incidents (and which were closed as noise) is what makes the actionability rate computable — without the join, unactioned pages are invisible.
5. **Publish per-team trend dashboards, not global averages.** A four-week rolling view of MTTA, actionability, and pages-per-shift per team lets each rotation see its own trend; global averages hide the one burning team behind everyone else's fine numbers.

## Targets and review cadence

1. **Set explicit, negotiated targets.** Reasonable starting points are MTTA under 5 minutes for pages, actionability above 50%, pages per shift under 2, and escalations under 10%; publish them next to the actuals so the gap, not opinion, drives work.
2. **Run a monthly alert review.** A standing 30-minute review of the top 10 noisiest rules, their actionability, and their owners is the single highest-leverage ritual; each rule leaves the meeting tuned, silenced, or deleted with a named owner.
3. **Delete or downgrade systematically.** A rule whose actionability has been below threshold for a full quarter should be demoted from page to ticket or deleted outright; unused severity is a tax every responder pays on every page.
4. **Attribute improvements to changes.** When grouping, inhibition, or threshold changes land (see `alert-grouping-patterns.md`, `alert-inhibition-rules.md`), annotate the dashboards so the next review can verify the change actually moved the metric rather than assuming it did.
5. **Feed the metrics back into rotation design.** Rising MTTA on night shifts or escalating pages-per-shift are staffing and schedule signals, not personal failures; use them as inputs to rotation sizing, follow-the-sun changes, and escalation-policy redesign.

## Pitfalls in interpretation

1. **Auto-acknowledgment games MTTA.** Scripts or bots that acknowledge pages flatter the metric while removing the human from the loop; exclude bot events from MTTA calculations or track human-only acknowledgment separately.
2. **MTTR inflates through forgotten resolves.** Pages left open for days (or resolved only when the auto-resolve timer fires) dominate the mean; use median or percentile resolution times and track the auto-resolve fraction as its own smell.
3. **Speed is not quality.** A fast-acknowledged, never-actioned page scores well on MTTA while contributing pure fatigue; always read MTTA next to actionability, never alone.
4. **Blame rotates people, not systems.** Per-team dashboards exist to fix rules and routing; the moment MTTA becomes an individual performance measure, the data gets gamed and the tool becomes useless.
5. **Survivorship bias hides the worst alerts.** Alerts that never page anyone (disabled by a silencing rule and forgotten) or fire only into chat are absent from lifecycle exports; periodically audit configured-but-muted rules so the metrics describe the whole system, not just the loud part.
