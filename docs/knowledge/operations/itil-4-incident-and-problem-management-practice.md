# ITIL 4 Incident and Problem Management Practice

## Purpose

In ITIL 4, incident management and problem management are separate practices with related but distinct goals. Incident management restores the agreed service quality as quickly as possible; problem management identifies and addresses the underlying causes of incidents and prevents their recurrence. Treating the two practices together, while keeping them procedurally distinct, is the operational pattern ITIL describes. This article summarizes how the two practices interact and how they fit into a modern service-management program.

## Incident management

Incident management covers the events that interrupt or reduce service quality. Its primary outcomes are:

- rapid restoration of service to the agreed level, not necessarily the identification of the root cause;
- accurate incident records with timing, ownership, and customer impact;
- closure, including confirmation that the user can perform the work they were trying to do.

Severity and priority are inputs into the workflow. Severity reflects the technical impact; priority reflects business impact combined with urgency. Where a single incident affects multiple services, the priority framework should still produce a single overall priority that drives initial response. Incident communications follow the agreed protocol: status updates at the documented cadence, with channels and templated language.

A common operational pitfall is resolving incidents without capturing the underlying cause. Incident resolution is not the same as incident closure; closure requires the agreed record complete, the agreed communications completed, and any follow-up actions scheduled.

## Problem management

Problem management covers the causes of one or more incidents. Its primary outcomes are:

- identification of problems through incident correlation, trend analysis, and supplier inputs;
- documented root-cause analysis, including the evidence supporting the root-cause conclusion;
- corrective action that prevents recurrence or reduces the probability or impact of recurrence;
- closure only when the problem is verified as resolved by measured observation.

Some organizations split problem management into reactive problem management (driven by incidents already seen) and proactive problem management (driven by availability, performance, or vendor signals). Both halves should be present.

## Difference between a workaround and a fix

A workaround reduces or removes the impact of a problem without addressing its root cause. A workaround is appropriate to incident management and is appropriate to problem management only as the short-term response. A fix addresses the root cause and is what closes the problem. Workarounds should have owners and reviews so they do not silently become the durable "solution".

## Workflow between the two practices

1. Open an incident record at the moment service quality drops.
2. Restore service via workaround where possible; record what was done.
3. At incident closure, decide whether the residual is acceptable. If not, open a problem record.
4. Investigate the problem; collaborate with suppliers, engineering, and security as needed.
5. Identify the root cause and define a corrective action.
6. Implement the corrective action and verify the outcome, including that related incidents have stopped or fallen.
7. Close the problem with evidence of recurrence reduction.
8. Update known-error records where a workaround exists for an unresolved root cause.

## Roles

Both practices benefit from clear role separation:

- **Incident commander** — owns the live response; coordinates actions and communications.
- **Technical lead** — owns the technical investigation; brings in suppliers or engineering as appropriate.
- **Problem manager** — owns the problem record end to end; coordinates the corrective action.
- **Major incident reviewer or manager** — for incidents that escalate, owns the post-incident review and tracks follow-up to closure.

A small service can combine these roles, but the responsibilities should remain distinct in writing. The reason for the distinction is to ensure that no single role is responsible for both fast restoration and methodical investigation at the same moment.

## Validation evidence

Validation evidence includes incident and problem records with timing and ownership, post-incident reviews with corrective actions, problem records with root-cause analysis, corrective-action plans with owners, known-error database entries, supplier incident reports for third-party-caused incidents, and trend reports showing incident and problem patterns. The most useful evidence is the chain from a known incident to a known error to a closed problem.

## Failure modes

Failure modes include incident teams solving workarounds that become the durable solution, root causes being declared without evidence, problem records being opened and never closed, supplier incidents being treated as if they were internal, and incident management being trained and problem management being neglected.

## Working with supplier incidents

When an incident originates with a third-party supplier, the rules of the practice still apply. The on-call engineer represents the customer side; the supplier represents its own operations. A useful operational pattern is to require that supplier incidents follow the same opening, communication, and closure disciplines the internal practice uses. The artifact language should be visible to both parties, the impact description should reflect the consumer's experience, and the closure should explicitly indicate whether the supplier considers the incident resolved. Going further, supplier contractual terms should require supplier incidents to flow through the practice interfaces described here; without this, third-party incidents become slack for both sides.

## Major-incident patterns

For incidents classified as major — large user impact, regulatory exposure, or cross-organization blast radius — the practice should default to a defined major-incident procedure. A documented procedure ensures that the response activates the right roles, raises the right communications cadence, escalates to the right decision authority, and produces the right evidence for the post-incident review. The major-incident procedure is rarely invoked, which makes it a candidate for periodic desk exercises; the exercise record is itself evidence that the practice is operationally ready.

## Canonical sources

- PeopleCert, ITIL 4 incident and problem management qualification scheme: https://www.peoplecert.org/browse-certifications/it-governance-and-service-management/ITIL-1/itil-4-foundation-2565
- Axelos, ITIL 4 practice library: https://www.axelos.com/itil-4-framework-overview
- ITIL 4 Foundation, Practice Guide (Axelos / PeopleCert publication): https://www.axelos.com/certifications/itil

## Scope note

This article summarizes ITIL 4 incident and problem management practices as a reference; it does not replace ITIL 4 publications or claim certification.
