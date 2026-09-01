---
title: "Deal Stage Definition"
owner: "Commercial Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Deal Stage Definition

## Purpose

Provide canonical, evidence-based definitions of commercial deal stages so that pipeline and forecast hygiene is consistent across teams, regions, and product lines, and so that exit preconditions, evidence requirements, and forecasting integrity are understood by everyone who touches an opportunity.

## Scope

This article applies to all customer-facing opportunities across the company: net-new sales, expansions, renewals (when treated as a separate forecast line), pilots expected to convert to paid, partner-sourced deals, multi-year commitments, and any material upsell or cross-sell motion. It applies regardless of whether the opportunity is tracked in CRM, in a partner system, or in a custom pipeline tool, and SHOULD be enforced wherever commercial data is aggregated.

## Requirements

- Each deal stage SHOULD have a documented definition, an entry precondition, an exit precondition, and the evidence required to support movement between stages.
- Stage advancement MUST NOT be driven by forecast target, quarter-end pressure, or aspirational thinking; it MUST be supported by verifiable customer-side evidence.
- Each stage SHOULD have a defined probability band or confidence indicator that is independent of the salesperson's personal optimism.
- Stage definitions SHOULD distinguish between evidence categories: customer-confirmed (e.g., signed document, recorded approval), customer-indicated (e.g., verbal commitment, email intent), and inferred (e.g., "they've been responsive, so they probably will sign").
- Reverse movement (i.e., a deal moving backward in stage) SHOULD be supported by a documented trigger, not by silent editing of the stage field.
- Closed stages SHOULD distinguish closed-won from closed-lost with a mandatory loss-reason capture for the latter.

## Workflow

When a deal is created, it is placed in an entry stage with limited forecasting weight. As the deal progresses, the account team SHOULD record stage-relevant evidence: stakeholder identification, identified economic buyer, defined problem/use case, evaluated solution, security/privacy review status, procurement engagement, contracting progress, and signed commitment. Movement between stages SHOULD be timestamped with the user who made the change and the evidence supporting the change. Each forecast checkpoint SHOULD reconcile the stage of each material opportunity with the actual evidence in the deal record; discrepancies SHOULD be flagged for review. Where deals share a customer or stakeholder, the cumulative position SHOULD be reviewed to avoid double counting and to ensure consistent commercial posture.

## Controls

- Stage definitions MUST be documented in a single source of truth and SHOULD be reviewed at least annually for fitness.
- Movement of a material deal from a low-confidence stage to a high-confidence stage SHOULD require additional review (manager approval, deal-desk check, or forecast-committee review) to prevent unsupported upgrades.
- Forecast bias review (per related policy) SHOULD sample stage movements and test whether they correlate with forecast-pressure events (quarter-end, year-end, target-shortfall periods).
- Discrepancies between reported stage and observed evidence SHOULD be investigated and resolved before the deal contributes to the forecast.
- Closed-lost deals SHOULD be retained with loss-reason capture for trend analysis (per the related loss-reason policy).

## Forecasting integrity considerations

Stage definitions exist to support honest forecasting, not optimistic labeling. Pressure to meet a number MUST NOT justify moving an opportunity forward without evidence. Conversely, hiding a deal's true stage to manage internal optics is itself a governance failure. Forecast reviewers SHOULD test whether each material deal's stage is consistent with the latest available evidence, including any post-meeting notes, customer emails, and procurement-portal status. Deals SHOULD be re-staged when material new evidence arrives, including evidence that pushes the deal backward (e.g., a stalled procurement, a budget cut, a stakeholder change).

## Antitrust and coordination guardrails

Stage definitions and forecasting data MUST NOT be used to coordinate with competitors on pricing, market allocation, or customer treatment. Internal competitive-intelligence artifacts used in stage management MUST be limited to publicly available information or information lawfully obtained through legitimate channels. Cross-customer signal aggregation SHOULD NOT be used to infer or establish collusive pricing patterns. Where commercial terms depend on competitive context, the rationale MUST be defensible based on the company's own market view, not on competitor-disclosed pricing.

## Renewal as a deal stage

Renewals SHOULD be tracked as their own pipeline where the renewal decision is non-trivial (material price change, scope change, competitive re-evaluation, customer reorganization). A renewal is not "closed-won by default" simply because the prior contract anniversary is approaching; it SHOULD have its own qualification, its own evidence, and its own close path. Renewal qualification SHOULD consider usage, value-realization evidence, stakeholder sentiment, competitive alternatives, and the customer's own budget posture.

## Canonical sources

- SEC, Revenue Recognition — https://www.sec.gov/oca/revenue-recognition
- Federal Trade Commission, Antitrust Guidance — https://www.ftc.gov/industry/advertising-and-marketing/antitrust-guidance
