---
title: "Platform Roadmap Alignment"
owner: "Strategy Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Platform Roadmap Alignment

## Purpose

Ensure the platform roadmap is a faithful expression of strategic posture rather than a wish list disconnected from it. Platform investments have long lead times, sunk costs, and downstream lock-in, so the cost of a misaligned roadmap is high. This policy establishes the dependency mapping, sequencing rules, evidence standards, and review cadence that keep the platform roadmap aligned with strategy.

## Scope

This policy applies to platform-level investments that affect multiple products, customers, or operating models. It covers dependency mapping, sequencing, evidence standards, review, and the process for surfacing strategic change into the platform roadmap. It does not direct individual product-roadmap decisions, which follow product-level governance.

## Requirements

- Each platform investment MUST be traceable to one or more strategic objectives; investments that cannot be traced MUST be flagged as exploratory and SHOULD NOT consume the platform capacity envelope reserved for strategic commitments.
- Dependency mapping MUST identify internal platform dependencies, third-party dependencies, regulatory dependencies, and talent dependencies; the map MUST be updated whenever a material dependency shifts.
- Sequencing MUST respect critical-path analysis: investments that unblock higher-leverage commitments SHOULD be prioritised over investments whose standalone value is larger but whose downstream value is smaller.
- Evidence standards MUST be defined at commitment and MUST include at least one customer-impact validation, one integration test, and one operating-model readiness test.
- Major platform investments SHOULD be staged so that capital is released against demonstrated milestones; each stage MUST have an explicit decision point where the committee may continue, adapt, or stop.
- The platform roadmap MUST be reviewed at a cadence appropriate to its horizon, typically semi-annually, with an event-driven review whenever a strategic assumption fails or a material dependency shifts.
- Strategic change MUST flow into the platform roadmap through a controlled process; ad hoc changes outside the process MUST be escalated for explicit approval.

## Workflow

1. The platform owner maintains a roadmap that maps each investment to its strategic objectives and dependencies.
2. The platform owner proposes sequencing based on critical-path analysis, capacity constraints, and customer-impact validation.
3. The strategy committee reviews the proposed sequencing; the committee may reorder, defer, or stop investments based on strategic priority and capacity.
4. Approved sequencing is communicated to product teams; product teams align their own roadmaps to the platform sequencing rather than the reverse.
5. The platform owner reports progress against milestones at the agreed cadence; deviations are recorded with explanation and corrective action.
6. At each major review, the committee retests the alignment between the platform roadmap and the standing strategic posture.

## Controls

- Traceability: every major platform investment MUST carry a citation to the strategic objective it serves; uncited investments MUST be flagged.
- Capacity discipline: the total platform capacity envelope is set by the strategy committee; overruns require committee approval rather than absorption into other budgets.
- Change discipline: changes to sequencing outside the standing review require a written justification and approval by the strategy committee chair.

## Strategic drift and realignment

A platform roadmap that gradually drifts away from the strategic posture it was originally built to serve is a common failure mode, particularly in organisations with strong platform cultures. The drift typically happens through a series of individually defensible decisions: a feature added for one customer is generalised, a dependency that was acceptable for a single use case becomes the default for all, and the platform accretes capabilities that are useful but not strategic. The alignment review SHOULD therefore test not only whether current investments serve current objectives, but whether the cumulative shape of the roadmap still resembles the strategic posture, and SHOULD flag drift explicitly so the committee can choose between retro-fitting the platform or rewriting the strategy to match the platform reality.

Realignment decisions SHOULD be paired with explicit migration plans: when a strategic shift requires the platform to move away from a capability that has internal customers, those customers need a transition path or the strategic shift will be blocked by the operating reality. The migration plan is treated as part of the platform commitment, not as an afterthought.

## Platform economics

A platform investment that cannot be justified on its economics, separate from the products that depend on it, tends to be perpetually re-justified through the products rather than through its own contribution. The platform owner SHOULD therefore maintain a platform-level view of cost and value: what the platform consumes, what it returns to the products that depend on it, and what internal rate of return it generates on its investment. This view is not a substitute for product-level economics but a complement, and the committee SHOULD review both at the standing cadence to ensure that the platform's economics are sustainable without subsidy from any single product.

The platform economics SHOULD also distinguish between shared infrastructure that all consumers benefit from and bespoke capabilities built for individual consumers; the former is a candidate for shared cost recovery while the latter is a candidate for direct cost attribution. Confusing the two tends to over-recover from small consumers and under-recover from large ones, and tends to obscure the actual economics of platform investment; the refresh review SHOULD test whether the cost attribution is correctly aligned with the consumer benefit.

## Canonical sources

- ISO 56000:2020, "Innovation management — Fundamentals and vocabulary." https://www.iso.org/standard/69015.html
- OECD, "Digital Economy Outlook" (general reference for platform strategy and policy). https://www.oecd.org/digital/digital-economy-outlook.htm
- Gartner, "Platform Engineering Guidance" (general framework reference). https://www.gartner.com/en/articles/platform-engineering
- McKinsey, "Platform Strategy and the Business of Ecosystems." https://www.mckinsey.com/capabilities/quantumblack/how-we-help-clients/platform-strategy
