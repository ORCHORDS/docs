---
title: "Strategic Anchor Metrics"
owner: "Strategy Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Strategic Anchor Metrics

## Purpose

Define the standards for selecting and operating strategic anchor metrics so that the small number of metrics that frame strategic judgement are credible, well-instrumented, and resistant to gaming. Strategic anchor metrics are the few measurements on which executives anchor decisions; if they are wrong, the decisions that follow are wrong in a coordinated way. This policy establishes the discipline that protects them.

## Scope

This policy applies to the small set of metrics designated as "strategic anchor" within the broader metric hierarchy. It covers selection criteria, instrumentation integrity, recertification cadence, and ownership. It supplements [Strategic Metrics Governance](STRATEGIC_METRICS.md) by adding depth specifically for the anchor tier.

## Requirements

- Strategic anchor metrics MUST be few in number; an anchor metric SHOULD be added only when an existing metric cannot credibly answer the strategic question at hand.
- Each anchor metric MUST have a documented definition, an instrumentation owner, a data lineage record, and a recertification cadence.
- Selection criteria MUST include: strategic relevance, leading or lagging indicator clarity, robustness against metric gaming, alignment with the operating reality, and resistance to misinterpretation.
- The instrumentation MUST be auditable; the lineage MUST show the path from the operational source to the published number.
- Anchor metrics SHOULD be paired with counter-indicators that detect when the anchor metric is being achieved in a way that creates harm elsewhere.
- Recertification cadence MUST be defined at adoption and SHOULD be at least annual; more frequent recertification is required if the underlying data source changes.
- The instrumentation owner MUST be named and accountable for the integrity of the number; the strategy committee owns the framing and the interpretation.
- Anchor metrics MUST NOT be modified between reviews except through the formal change process; ad hoc redefinition is prohibited.

## Workflow

1. The strategy lead identifies a candidate anchor metric and prepares a definition packet that includes selection criteria, instrumentation, lineage, and counter-indicators.
2. The lead validates the packet with finance, data, and operations; disagreements are recorded in the dissent section.
3. The strategy committee reviews the packet and either approves, defers, or rejects the candidate.
4. On approval, the metric is added to the anchor register with metadata; derivative reporting cites the register rather than restating the definition.
5. At each recertification, the instrumentation owner reports on data quality, lineage changes, and any evidence of gaming; the committee decides whether to continue, amend, or retire the anchor.
6. Changes to anchor metrics between recertifications require a written justification and committee approval.

## Controls

- Definition integrity: the definition of an anchor metric MUST NOT change without a written justification and committee approval.
- Counter-indicator discipline: each anchor metric SHOULD be paired with at least one counter-indicator; the absence of a counter-indicator is an escalation event at recertification.
- Retirement discipline: retired anchor metrics MUST be archived with their final value and rationale; downstream reporting MUST NOT continue to cite them as if current.

## Anchoring and decision quality

Anchor metrics do their job precisely because they are few: they focus attention and reduce the cognitive load of strategic judgement. The cost of that focus is that the metrics can be over-weighted in decisions for which they are only partial evidence. The committee SHOULD therefore record, at each decision that relies on an anchor metric, the role the metric played in the decision: was it the primary evidence, a confirming signal, or one input among several? This record makes it possible, over time, to detect whether anchor metrics are crowding out other evidence in a way that produces systematically poor decisions, and to recalibrate the anchoring.

The metric selection SHOULD also test for second-order effects. Metrics that are easy to move in the right direction but that have ambiguous underlying mechanisms are vulnerable to optimisation against the metric rather than against the underlying outcome. The committee SHOULD require, at adoption, a brief statement of the causal theory behind each anchor metric: what is the mechanism by which moving the metric moves the outcome, and what evidence supports that mechanism. The causal theory is part of the metric definition and is recertified alongside the metric.

## Canonical sources

- OECD, "Guidelines on Measuring Trust." https://www.oecd.org/governance/measuring-trust.htm
- COSO, "Enterprise Risk Management — Integrating with Strategy and Performance." https://www.coso.org/Pages/default.aspx
- McKinsey, "The Usefulness of KPIs: A Framework for Choosing the Right Metrics." https://www.mckinsey.com/capabilities/operations/our-insights
- Harvard Business Review, "Be Careful with Your Balanced Scorecard" (general guidance on metric discipline). https://hbr.org/
