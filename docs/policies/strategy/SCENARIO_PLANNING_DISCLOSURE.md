---
title: "Scenario Planning Disclosure"
owner: "Strategy Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Scenario Planning Disclosure

## Purpose

Set the disclosure controls for scenario-planning outputs so that internal scenario work informs decisions without leaking partial, speculative, or sensitive content in a way that misleads internal or external audiences. Scenario work is by nature uncertain, and without disciplined disclosure it is regularly read as forecast rather than as conditional exploration.

## Scope

This policy applies to scenario-planning artifacts, including scenario narratives, assumption sets, sensitivity tables, scenario dashboards, and derivative narratives derived from them. It covers audience scoping, embargo, retraction, and recertification. It does not govern the analytic methodology itself, which is described in [Scenario and Assumption Management](SCENARIO_ASSUMPTION_MANAGEMENT.md).

## Requirements

- Each scenario artifact MUST be classified as internal-only or restricted; the classification MUST be set at creation and recorded in the artifact's metadata.
- Internal-only artifacts MAY be shared within the strategy committee and named working groups; restricted artifacts require a named distribution list approved by the strategy committee chair.
- Embargo periods MAY be applied to scenarios that depend on non-public inputs or that could move markets if disclosed prematurely; the embargo MUST be recorded with rationale and owner.
- Scenarios MUST be presented as conditional explorations rather than as forecasts; the language of the artifact MUST distinguish "if-then" statements from "will" statements.
- Each artifact MUST carry a recertification date and MUST be retracted or refreshed once that date has passed; stale scenarios MUST NOT be cited as if current.
- Retraction MUST be communicated through the same channels as the original distribution; partial retraction is prohibited.
- Where a scenario is used as the basis for an external communication, the communication MUST explicitly state that the underlying scenario is conditional and MUST NOT present the conditional outcome as expected.

## Workflow

1. The scenario author assigns a classification at creation and records rationale in the metadata.
2. The author drafts the artifact using the standing template and labels each assumption and conditional outcome explicitly.
3. The strategy committee (or chair, for restricted artifacts) reviews the classification and the distribution list; the committee may revise the classification if the artifact's sensitivity warrants.
4. The artifact is distributed according to the approved list; the distribution is logged with recipients and date.
5. At recertification, the author determines whether the scenario stands, requires revision, or must be retracted; the determination is recorded and communicated.
6. If a retraction is required, the author communicates it through the same channels as the original distribution within an agreed window.

## Controls

- Classification integrity: changing the classification of an existing artifact requires committee approval and a written justification.
- Recertification discipline: artifacts that have passed their recertification date MUST be withdrawn from circulation; the originating team is responsible for executing the withdrawal.
- Source protection: scenarios MUST NOT contain identifiable information about non-public inputs that, if disclosed, would breach confidentiality or legal obligations.

## Communication discipline

The most common disclosure failure with scenario work is not external leak but internal misuse: a conditional narrative is presented to a downstream audience as a forecast, and that audience builds operational plans on the conditional outcome. To reduce this risk, derivative communications SHOULD carry a brief origin tag linking back to the artifact and its recertification date, and SHOULD preserve the conditional language of the source. Training in scenario interpretation SHOULD be provided to audiences that consume scenario output as part of their regular workflow; the training emphasises the difference between conditional exploration and forecast, and the appropriate behaviours that follow from each.

When a scenario triggers a decision, the decision record SHOULD reference the scenario by identifier and recertification date, and SHOULD record which conditional branch the decision was predicated on; this makes it possible, at the next recertification, to revisit decisions whose underpinning scenario has been withdrawn.

## Working with external parties

Scenario work sometimes requires input from external parties, including subject-matter experts, customer representatives, and partner organisations. When external input is used, the input provider SHOULD be informed of the conditional nature of the work and SHOULD be given the opportunity to review how their input has been characterised in the artifact. This protects the integrity of the input and reduces the risk that an external party is later surprised, or concerned, by how their contribution has been used; the reviewer's comments SHOULD be recorded in the artifact's provenance record alongside the input itself.

Where scenario work is co-developed with another organisation, the disclosure controls of both organisations apply, and any divergence SHOULD be resolved in writing before the artifact is distributed. A scenario that has been approved under the standards of one organisation but not the other SHOULD NOT be circulated to the joint audience; the resolution process is the appropriate response.

## Canonical sources

- OECD, "Strategic Foresight" topic page. https://www.oecd.org/strategic-foresight/
- Shell, "Scenario Planning" general methodology reference (publicly published scenario work archives). https://www.shell.com/energy-and-innovation/the-energy-future/scenarios.html
- McKinsey, "A Guide to Scenario Planning." https://www.mckinsey.com/capabilities/strategy-and-corporate-finance/how-we-help-clients/strategy
- ISO 31000:2018, "Risk management — Guidelines." https://www.iso.org/standard/65694.html
