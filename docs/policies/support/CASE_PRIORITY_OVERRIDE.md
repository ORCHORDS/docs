---
title: "Case Priority Override"
owner: "Support Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Case Priority Override

## Purpose

Define the authority, evidence, and review required to depart from the priority assigned by the documented case-classification rules, so that overrides are deliberate, traceable, and reversible rather than a workaround that bypasses the prioritization framework.

## Scope

This article covers every change to a case's documented priority, severity, escalation tier, or service-level target — including the raising of priority above what classification would otherwise assign, the lowering of priority below what classification would otherwise assign, and any change to a target response or resolution time outside the published service levels. It applies to all support channels and to cases handled directly by a named agent, by a queue, by an automated triage tool, or by an AI-assisted agent working under human supervision. It does not change the underlying classification rules, which sit in the case-classification policies.

## Why overrides exist

The classification rules are designed to be applied consistently across many cases and many agents; they cannot anticipate every customer-impact signal. Some signals — active loss of access, safety-relevant failure mode, repeat high-impact defect, regulator engagement, or coordinated abuse — warrant priority treatment even if the underlying classification would otherwise assign lower urgency. Other signals — known duplicate case, customer explicitly asks for slower cadence, ambiguity resolved in favor of the customer — warrant lowering priority. Overrides exist to honor those signals without rewriting the framework, but they MUST be governed so that they cannot be used to silently bypass the queue or to favor individual customers.

## Requirements

An override MUST be approved by an agent with documented override authority for the case type and the direction of the change. The approver MUST be independent of the agent who originated the request, except in narrow, pre-approved scenarios (for example, a designated on-call engineer raising priority for a single production incident under standing rules). The override MUST record, at minimum, the case identifier, the priority before and after, the reason category selected from an approved list, the specific evidence supporting the override, the identity of the approver, the time of the change, and any time limit after which the override auto-expires and the case returns to its classification-driven priority.

The recorded reason MUST be specific. Generic entries such as "VIP," "goodwill," or "management request" MUST NOT be used as the sole justification. Where an override is based on customer identity, contractual tier, or commercial relationship, the override MUST reference the documented tier or commitment and the policy under which it applies, and the relationship MUST be reviewable by audit.

Over-ride use SHOULD be capped. Sustained override rates above documented thresholds (for example, more than a defined percentage of cases in a queue, or repeated overrides of the same case across a window) MUST trigger an after-action review by the support-lead function and, where patterns persist, a revision to the underlying classification rules rather than continued reliance on individual exceptions.

## Evidence required

For raising priority, evidence SHOULD include at least one objective signal — a reproduction link, a log excerpt, a status-page event, a defect identifier, a regulator or auditor reference, an abuse report, or a comparable artifact — together with a one-sentence statement of the customer impact if the case is not raised. For lowering priority, evidence SHOULD include the customer request, the duplicate-case linkage, the resolution path that does not require the prior target, or the equivalent. Hearsay alone MUST NOT be sufficient for either direction.

## After-action review

When an override is used to close a case earlier than the documented target, or when the case later escalates, the override MUST be reviewed by the support-quality function. Reviewers MUST assess whether the original evidence was adequate, whether the approver was independent, and whether the classification rules need revision to absorb the case type. Findings MUST be aggregated at the queue and team level and reported to support leadership on the same cadence as other quality metrics. Repeated inadequate overrides by the same agent or approver MUST trigger coaching, additional approval, or revocation of override authority.

## Customer-facing implications

Overrides that affect a published commitment to a customer MUST be reflected in the customer-visible communication where the commitment was made, in language the customer can understand. A reduction in priority MUST NOT be communicated in a way that suggests the customer's case has been deprioritized because of who they are or what they asked. A raise in priority that is material to a service-level commitment MUST be honored as if it were the case's original priority.

## Canonical sources

- ITIL 4 Foundation, *Service Level Management practice*, https://www.axelos.com/certifications/itil-service-management/itil-4-foundation
- HDI Support Center Standards, https://www.thinkhdi.com/standards
- ISO/IEC 20000-1:2018, Information technology — Service management, https://www.iso.org/standard/70636.html
- INCITS/ISO/IEC 20000-1 overview, https://www.iso.org/standard/70636.html
