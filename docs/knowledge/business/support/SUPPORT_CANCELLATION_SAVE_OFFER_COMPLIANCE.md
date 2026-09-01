# Support Cancellation Save-Offer Compliance

When a customer asks to cancel, a save desk swings into action: it may listen, diagnose, and offer an alternative that genuinely fits. The line between legitimate retention service and unlawful interference is thin and heavily regulated. A cancellation that the company makes hard to complete, buries in conditions, or trades against pressure tactics is not a save; it is a conversion funnel wearing a service costume. This article defines the compliance discipline for save offers at the support desk.

## Scope

This article covers the handling of cancellation requests and the use of save offers: honoring the cancellation, recording offers accurately, prohibited conduct, and verification that cancellations complete as requested. It applies to any support channel that receives cancellation or discontinuation requests for subscription or recurring services.

It does not cover win-back marketing after cancellation, debt collection, general renewal pricing, or the commercial design of retention offers. It assumes the governing consumer protection rules of the customer's jurisdiction apply and that the desk treats the strictest applicable rule as its floor when jurisdictions mix.

## Workflow or implementation guidance

The save workflow runs in seven steps:

1. Recognize and register. Any statement of intent to cancel, however phrased, is treated as a cancellation request: it is registered with a timestamp and the channel that carried it. The register entry exists before any save attempt begins, because the request's legal clock starts when the customer communicates it, not when the company acknowledges it.
2. Confirm scope simply. The agent confirms what the customer wants to end (which subscription, effective when) using plain questions. Obstacles, quizzes, and persuasion are not part of this step.
3. Execute first, or offer once, as policy directs. Where the desk's policy permits a save attempt, it is a single, clearly labeled offer presented after the cancellation is fully processed or with the cancellation remaining fully in force; the offer never conditions, delays, or gates the cancellation itself. The customer must be able to decline and be done.
4. Offer content rules. A save offer states its terms plainly: price, duration, what changes, when it reverts, and that declining has no consequence. Offers involving a pause, a downgrade, or a plan change state what the customer keeps and loses. No offer may be presented as urgent, expiring-in-minutes, or available only if the customer cancels the cancellation now.
5. Recording. Every save interaction records: the cancellation request timestamp and text, the offer terms as presented, the customer's response, the final state (canceled, saved, deferred by explicit customer choice with a stated date), and the agent identifier. If the customer declines, the record shows a clean cancellation with its effective date. If the customer accepts, the record shows affirmative consent to the specific terms, captured by the same means the customer used to communicate.
6. Confirmation to the customer. The customer receives a confirmation of the outcome in the same channel (or a durable channel if they choose), restating the final state, the effective date, any refund due, and how to reverse an accepted save offer within a stated window.
7. Completion verification. Within a defined period after the effective date, the desk verifies the cancellation took effect: billing stopped, access changed as agreed, refunds issued. Failures route to a remediation queue with a deadline.

Prohibited conduct is enumerated rather than implied: requiring a phone call to cancel when signup was online; repeated retention scripts after a decline; guilt or fear framing; misrepresenting the consequence of cancellation; offers that require the customer to affirmatively reject multiple alternatives; charging for the cancellation period beyond what the terms allow; and any interface pattern whose obvious purpose is fatigue rather than choice.

## Controls

- Request-clock integrity: the register timestamps the request at first communication, and any internal SLA for processing cancellations is measured from that timestamp.
- Single-offer rule enforcement: the system counts save attempts per request; more than one offer per cancellation request is an exception requiring supervisor justification.
- Prohibited-pattern review: save scripts, macros, and flow designs are reviewed against the enumerated prohibitions before use, and periodically re-reviewed as rules evolve.
- Recording completeness: a monthly sample of save interactions is checked for full records (request, offer terms, response, final state); incomplete records are treated as compliance defects, not clerical gaps.
- Completion audit: the verification step's findings (stopped billing, issued refunds) are reported monthly; any cancellation found still billing is remediated and the customer is made whole, with root cause recorded.
- Dark-pattern intake: a standing feedback path lets customers and agents report cancellation friction; reports are triaged with the same severity discipline as service defects.

## Validation evidence

Evidence the save desk is compliant: the cancellation register with timestamps, outcomes, and time-to-effect; save-offer counts per request showing the single-offer rule holding; sampled interaction records with complete offer terms and responses; script and flow review sign-offs; the monthly completion audit with remediation outcomes and root causes; and complaint or regulator-contact trends on cancellation friction. A periodic test cancels a real internal account through each public path (web, email, phone, chat) and measures the obstacles encountered, with the transcript retained as the artifact; this is the most direct evidence that the published path matches the legal duty.

## Failure modes and correction

The gauntlet is the primary failure: the cancellation path accumulates steps, holds, and required conversations, and completion rates fall while "saves" rise. Correction: the periodic path test, completion-rate monitoring by channel, and removal of any step whose only function is friction.

The unrecorded offer is second: an agent presents terms verbally, the customer accepts, and no record of the actual terms exists; disputes then favor whatever was not written. Correction: recording-completeness sampling and a rule that verbal offers are read from approved text whose content is logged.

The phantom save is third: the customer declines the offer but the system records a save (plan changed rather than canceled), and billing continues. Correction: final-state reconciliation and the completion audit, with automatic remediation.

The expiring-pressure offer is fourth: terms presented as now-or-never to force a decision the customer would not make deliberately. Correction: prohibited-pattern review and removal of urgency framing from approved scripts.

## Limitations

Rules differ by jurisdiction and change over time; this article fixes the discipline, not the legal content, and the desk must map its actual obligations with counsel. Business-to-business contracts may permit negotiated exit processes that would be unlawful facing a consumer; the register must distinguish them so consumer protections are never diluted by analogy. Verification of completion depends on billing system integrity and its change windows. Finally, none of this converts a bad product into a retensible one; a compliant save desk still leaks customers whose problem was never the price.

## Canonical sources

- FTC, Negative Option Rule (Rule Concerning Recurring Subscriptions and Other Negative Option Programs), https://www.ftc.gov/legal-library/browse/rules/negative-option-rule
- FTC, Business Guidance (Bureau of Consumer Protection Business Center), https://www.ftc.gov/business-guidance
- W3C, Web Content Accessibility Guidelines (WCAG) 2.2, https://www.w3.org/TR/WCAG22/
