# sla-reporting-to-customers

**Issue:** example project's enterprise contracts promise 99.9% monthly uptime with tiered service credits, but when a customer's account manager asks "did we meet the SLA for acme-corp in July, and what do we owe them," nobody can answer for three days. The uptime dashboard shows a fleet-wide average, not per-tenant measurement; the contract excludes planned maintenance and "factors outside our reasonable control," but the measurement pipeline excludes nothing; and the credit tiers in the contract (e.g. below 99.95% but at or above 99.0% yields a 10% credit) have no implementation anywhere. Customer-facing SLA reporting is a data product with legal and financial consequences — it needs its own measurement definitions, exclusions logic, audit trail, and report pipeline, distinct from internal SLO tooling.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Measurement definitions that mirror the contract

1. **Encode the contract's measurement window and formula exactly.** If the SLA says "monthly uptime percentage = successful requests / total requests measured per calendar month," the report pipeline computes precisely that — not synthetic probe availability, not fleet uptime, and not the internal SLO that uses a 30-day rolling window. Every divergence between contract text and pipeline code is a future dispute.
2. **Measure per customer scope, not per service average.** Enterprise SLAs usually bind specific regions, products, or API endpoints the customer actually uses. The pipeline needs tenant-scoped SLI series (filter by tenant ID / plan / region) with retention long enough to recompute any month for the life of the agreement plus the claim window.
3. **Define "successful request" before the first dispute.** Which status codes count (5xx only? 429s? gateway timeouts?), and what happens during customer-caused 4xx floods — write these into the SLA appendix and implement the same classification in one shared query used by both the report and the internal dashboard, so engineering and legal can never disagree about the number.
4. **Timestamps in UTC, months by contract calendar.** State the timezone and the month-boundary rule in the contract; edge incidents that straddle midnight on the last day of the month otherwise produce two "correct" numbers.

## Exclusions, credits, and the claim process

1. **Implement the exclusion ledger explicitly.** Planned maintenance windows (with advance-notice requirements), customer-caused faults, force majeure, and third-party outages the contract carves out must be recorded as explicit time intervals with justification links, then subtracted by the report engine — not hand-adjusted after the fact. An exclusion without a ledger entry does not exist.
2. **Compute credit tiers mechanically from the contract table.** Model the tier table (e.g. `>=99.95%: none; >=99.0%: 10% of monthly fees; >=98.0%: 25%; below: 30% or termination right`) as data, and generate the credit decision per account per month. Credits are usually the "sole and exclusive remedy" — mis-issuing them is a direct financial error in both directions.
3. **Automate the claim window.** Contracts typically require customers to request credits within ~30 days; the pipeline should flag eligible-but-unclaimed months and drive either automatic issuance or a reminder to the account team before eligibility expires. Silent non-payment of owed credits erodes trust exactly like uptime misses do.
4. **Reconcile internal SLO headroom against the SLA floor.** The internal SLO target must be strictly tighter than the contractual SLA (see `sli-slo-sla-definitions.md`), and the error-budget policy should treat "SLA breach imminent" as its most severe escalation trigger — the budget you are really protecting is the contractual one.

## The report pipeline and its audit trail

1. **Generate reports automatically, monthly, per account.** A scheduled job emits: uptime percentage per covered component, incident list with start/end timestamps, exclusions applied, credit determination, and a methodology appendix. Manual spreadsheet assembly is where disputes are born — one pipeline, versioned in the repo, is the single source of truth.
2. **Keep the evidence, not just the verdict.** Retain the raw per-request or interval SLI data (or a provably complete aggregate) so any number in the report can be recomputed later. Compliance-oriented customers — and frameworks like CMMC — increasingly demand evidence of measurement, and "service credits as sole remedy" does not substitute for proof.
3. **Freeze each report when issued.** The report as sent to the customer is immutable; corrections happen as versioned amendments. Backfilling numbers after customer pushback without history destroys the credibility of every future report.
4. **Expose an honest status page separately.** Proactive status communication reduces claims and churn, but keep the status page operationally honest rather than contractually precise — the SLA report, not the status page, is the legal artifact.

## Failure modes that cause disputes

1. **Measuring the wrong thing entirely.** Probe-based "uptime" that pings a landing page while the customer's API path was down produces a passing report and a furious customer. Measure the paths the contract covers, from locations representative of the customer's users.
2. **Partial-month onboarding churn.** A tenant activated mid-month is not accountable to a full-month SLA; apply pro-rating rules defined in the contract rather than computing a misleading percentage over 12 days of traffic.
3. **Exclusion creep.** Every incident tempts someone to reclassify it as "third-party/force majeure." Require a named approver and written justification per exclusion, and report exclusion totals to leadership monthly — a rising exclusion rate is an uptime problem wearing a disguise.
4. **Numbers that disagree across artifacts.** The customer-facing report, the internal SLO dashboard, and the incident postmortem will be compared line by line during a dispute. Ship from one underlying dataset with documented transformation rules; when they must differ (rolling vs calendar month), label both clearly so the difference is explained before it is discovered.
