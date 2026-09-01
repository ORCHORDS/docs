# SRE Service Level Objectives and Error Budget Policy

## Purpose

The Google SRE book and its companion SRE Workbook describe a model in which service reliability is managed through formal service-level objectives (SLOs), explicit error budgets derived from those objectives, and a policy that translates remaining budget into engineering and product decisions. This article summarizes that model at an engineering reference level so that SRE programs and platform engineering functions in any organization can use the terminology consistently and apply the policy deliberately.

## Definitions

- **Service Level Indicator (SLI)** — a measured quantity of the service, such as request success rate, request latency at the 99th percentile, or availability of a critical job.
- **Service Level Objective (SLO)** — a target value or band for an SLI over a defined window; the durability of the SLO is what makes it a useful engineering target.
- **Error Budget** — the allowed failure between 100% and the SLO target, expressed in minutes, occurrences, or requests; the budget is the conversion between reliability target and operational flexibility.
- **Service Level Agreement (SLA)** — a contractual or business-side commitment. The SLO is the engineering target; the SLA is the externally stated commitment; the SLO must usually be stricter than the SLA so that the business commitment can be honored with margin.
- **Burn Rate** — the rate at which the error budget is being consumed relative to the window. Burn-based alerting is what makes budgets operational.

These definitions are repeated across the SRE book and the SRE Workbook and are stable.

## Why a budget, not just a target

An SLO alone is a static goal; it is not operational. An error budget derived from an SLO is operational because it answers "how much unreliability can we tolerate for how long?" without constant reinterpretation. Without a budget, SLOs lose to optimistic launch decisions; with a budget, the launch decisions can be made on a common currency.

The budget also prevents the most common reliability failure: the team that thinks it is responding to "an urgent page" but is being driven by feelings rather than by remaining budget. When the budget is the language, the same facts drive the same actions.

## Workflow for SLO and budget

1. Define SLIs that match the customer's experience of the service. Avoid proxies that look like SLIs but do not measure user impact.
2. Define SLOs per SLI with windows (typically 28 or 30 days for service-level decisions, and shorter windows for burn-rate alerting).
3. Derive the error budget from the SLO target and the window.
4. Decide what the SLO excludes (planned downtime, internal traffic, dependencies that are measured separately) and document the decision.
5. Define the burn-rate alerting thresholds, usually 1x, 2x, and 6x burn, with explicit per-window denominators.
6. Define the policy for what happens when the budget is exhausted: freeze non-safety changes, prioritize reliability work, escalate, and so on.
7. Track burn history and budget exhaustion events to drive the next cycle of SLO adjustment.

## Burn-based alerting

Burn-based alerting uses the relationship between observed error and remaining time. For a 30-day budget, a 1x burn consumes the budget in 30 days; a 2x burn consumes it in 15. Multi-window burn-rate alerts are designed to balance sensitivity against false-positive pressure, typically by combining a short fast-burn window with a longer slow-burn window. The exact thresholds depend on the team and the incident data, but the principle is consistent across the SRE literature.

## Policy patterns

Common policy patterns include:

- **Release freeze** — when a service has exhausted its budget, freezing non-safety releases until reliability work restores the budget.
- **Risk acceptance** — when a business decision is made to ship despite low budget, documenting the risk acceptance explicitly, with named owners and a sunset date.
- **Budget transfer** — moving budget between services in a tier or product family to allow coordinated risk-taking.
- **Ceiling renegotiation** — renogotiating the SLO target and the window when the existing target is genuinely unachievable; do not lower the SLO without a justification that the SLO was the wrong target.

## Validation evidence

Validation evidence includes the SLO catalog with windows and exclusions, the SLI definition with measurement source, the error budget policy, the alerting configuration with burn thresholds, the burn history per service, and the action records following exhaustion events. The most useful evidence is the date a budget was exhausted, the response taken, and the action plan followed.

## Failure modes

Failure modes include defining SLOs that cannot be measured or that measure proxies unrelated to user impact, choosing windows that are too long for the cadence of the service, freezing releases after every minor budget event and creating eventual outage fatigue, and renegotiating SLOs downward on every miss. The model is most valuable when its policy is applied consistently.

## Canonical sources

- Google SRE Book, Service Level Objectives chapter and surrounding chapters: https://sre.google/sre-book/table-of-contents/
- Google SRE Workbook, sections on SLOs and error budgets: https://sre.google/workbook/table-of-contents/
- Google SRE, Service Level Objectives (web resource): https://sre.google/resources/

## Scope note

This article summarizes the SLO/error-budget model; it is not a replacement for the SRE book or workbook and does not claim that every organization must adopt the same model. Organizations should adapt terminology, windows, and policy based on their service portfolio.
