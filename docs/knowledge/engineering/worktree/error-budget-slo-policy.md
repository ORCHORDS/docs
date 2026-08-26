# error-budget-slo-policy

**Issue:** Teams argue about reliability without shared data: after every incident, one faction demands "no more outages ever" while the other keeps shipping features through the smoke. Chasing 100 percent reliability is both impossible and maximally expensive, yet operating with no target means nobody knows whether the service is actually healthy. The SRE answer is a pair of artifacts: a service level objective (SLO) that states how reliable the service must be for users to be happy, and an error budget — the complement of that target — that quantifies how much unreliability is acceptable. The error budget policy, canonical in the Google SRE Workbook and refined across the 2025 observability ecosystem, is the written agreement about what the team does when the budget is spent, burns fast, or is hoarded.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Foundational concepts

1. **SLIs are the measurements, SLOs are the targets.** An SLI (service level indicator) is a ratio of good events to total events, such as the fraction of requests served under 300 ms. An SLO is the target you set on that indicator, for example 99.9 percent over 28 days. Define SLIs first; targets without indicators are slogans.
2. **The error budget is 100 percent minus the SLO.** A 99.9 percent availability target grants a monthly budget of roughly 43 minutes of acceptable downtime or 0.1 percent failed requests. The budget is a resource to spend, not a failure to hide.
3. **Base budgets on SLOs, never SLAs.** SLA-driven budgets anchor to contract penalties and produce either reckless risk-taking (we have hours left before we owe money) or pathological risk-aversion. SLOs anchor to user happiness, which is the thing you actually want to protect.
4. **Users experience percentiles, not averages.** A p50 latency of 80 ms with a p99 of 8 seconds feels broken to the unlucky percentile. Choose indicators and windows that reflect the experience of real users of each critical journey.

## Setting SLIs and SLOs

1. **Start from user journeys.** Enumerate the handful of things users must be able to do (search, checkout, login) and attach SLIs to each journey's success rate and latency. An SLO with no journey behind it measures the wrong thing precisely.
2. **Keep the suite small.** Three to five SLIs per service is the practical ceiling. Every additional indicator dilutes attention and multiplies alert noise.
3. **Set targets from historical data, then tighten.** Begin with the achieved reliability of the last quarter, then ratchet. Targets plucked from ambition (five nines on a three-nines system) exhaust budgets instantly and destroy trust in the whole framework.
4. **Choose windows deliberately.** A 28-day rolling window smooths spikes and matches monthly planning; shorter windows make budgets twitchy. Whatever you choose, document it — window arithmetic disputes waste more meetings than target disputes.

## Writing the budget policy

1. **The policy is the pre-agreed consequence, not a vibe.** A real error budget policy states, in writing and signed by engineering and product leadership, what happens at each budget state. Deciding consequences during an outage guarantees an emotional outcome.
2. **Exhausted budget means reliability work first.** The standard clause: when the budget is spent, feature releases freeze (or require an explicit, logged exception from product leadership) and the team prioritizes reliability until the budget recovers.
3. **Fast burn triggers escalation.** Define burn thresholds — for example, consuming 5 percent of the 28-day budget in one hour — that page the on-call and open an incident, even if users have not complained yet.
4. **Unspent budget licenses risk.** The other half of the bargain: when the budget is healthy, the team ships aggressively, raises deploy frequency, and runs chaos experiments. A policy that only ever restricts will be quietly abandoned by the feature side of the house.
5. **Publish budget state continuously.** A dashboard showing remaining budget, burn rate, and current policy state keeps the agreement honest and removes the "are we okay?" Slack thread.

## Alerting on burn rate

1. **Alert on burn rate, not budget balance.** Multi-window burn-rate alerts (for example, a 14.4x burn sustained over one hour, or 3x over six hours) create urgency before exhaustion. SRE practice across 2025 tooling treats these as the default SLO alerting pattern.
2. **Pair a fast and a slow window.** The fast window catches sudden outages; the slow window catches slow leaks that never trip the fast one. Either alone has a well-known blind spot.
3. **Page only on budget-threatening burn.** Routine fluctuations belong in tickets and dashboards, not pagers. If SLO alerts fire more than a couple of times per quarter and the budget is fine, the thresholds are wrong.
4. **Automate the response where possible.** Budget spent should automatically gate deploys or open a reliability epic rather than relying on someone remembering the policy at 2 a.m.

## Governance and recalibration

1. **Review SLOs after significant incidents.** Postmortems should ask whether the indicator missed the user pain: if users were angry while SLIs were green, the SLI is decorative and must be redesigned.
2. **Recalibrate targets periodically.** Tighten SLOs when the budget is chronically hoarded; relax them when chronic exhaustion freezes roadmap for quarters. A target nobody can meet is a planning bug.
3. **Distinguish client, network, and dependent-service errors.** Attribute budget consumption to its source so a flaky upstream dependency does not silently consume your release velocity.
4. **Treat the policy as a living document.** Revisit the policy text twice a year with both engineering and product at the table; the framework survives only as long as both sides believe it is fair.
