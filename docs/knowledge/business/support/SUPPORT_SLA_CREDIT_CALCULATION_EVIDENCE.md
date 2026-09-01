# Support SLA Credit Calculation Evidence

When a support service level is missed, a credit may be owed. The credit is a financial consequence, so the calculation behind it must be reproducible: an auditor, a customer, and the finance team must each be able to re-derive the same number from the same inputs. This article governs the evidence chain for SLA credit calculations, from the clocks and data sources that establish the breach to the statement the customer receives.

## Scope

This article covers how the support desk calculates service-level credits for missed response and resolution commitments: the authoritative data sources, the clock definitions, exclusion handling, the calculation record, and the customer-facing statement. It applies wherever a support agreement ties a missed service level to a fee credit or remedy.

It does not cover the commercial negotiation of SLA targets, uptime credits for platform availability (a separate service-credit discipline), or goodwill gestures outside contracted remedies. It assumes the agreement text is available and that its terms are specific enough to compute; where terms are ambiguous, the ambiguity is escalated before calculation, not resolved silently in code.

## Workflow or implementation guidance

The calculation pipeline runs in seven steps:

1. Term extraction. From the executed agreement, extract the metric (first response, resolution, update cadence), the target per priority tier, the measurement method, the credit schedule (percentage per breach band, caps, accumulation), exclusions, and the claim or notification procedure. Each extracted term is quoted verbatim into the calculation worksheet with a clause reference; paraphrased terms are not permitted.
2. Event assembly. Pull the raw events for the case: the customer's inbound timestamp, queue timestamps, agent response timestamps, status transitions, pauses, and closure. The data source of record for each field is named (ticketing platform field, telephony log, mail gateway header), and the export is frozen and hashed once the case enters credit evaluation.
3. Clock construction. Build the measured interval from the terms: which timestamp starts the clock, which event stops it, business-hours versus continuous time, timezone (stated as UTC with the customer's local overlay), and holiday calendars applied. If the agreement is silent on a clock detail, the desk selects the interpretation favorable to the customer, records the choice, and initiates a contract clarification.
4. Exclusion application. Apply the agreement's exclusions (customer-caused delay, scheduled maintenance, force majeure, third-party outage, incomplete information from the customer) only with evidence: a customer-delay exclusion requires the pending-customer clock to have been active; a maintenance exclusion requires the maintenance window to have been published in advance. Every exclusion reduces the measured interval and is logged with its justification and the evidence pointer.
5. Breach determination. Compare the exclusion-adjusted interval to the tier target. Marginal cases (within the measurement system's timestamp granularity) resolve in the customer's favor, and the margin rule is written down.
6. Credit computation. Map the breach to the credit schedule, apply caps and accumulation rules, compute the monetary value against the correct fee base, and carry-forward any prior-period usage of the cap.
7. Statement issuance. Produce the customer statement: the case identifier, the metric missed, the start and stop timestamps in UTC and the customer's timezone, exclusions applied with reasons, the adjusted elapsed time versus the target, the credit percentage and amount, the cap status, and the remedy's application method (next-invoice credit or refund). The statement is issued by the deadline in the agreement's notification clause.

Every step writes to a durable calculation record. The record is the artifact of this discipline: term quotes with clause references, the frozen event export with its hash, the clock configuration used, exclusions with evidence links, the computation inputs and outputs, and the statement as sent. The record must be sufficient for an independent party to reproduce the credit without asking questions.

## Controls

- Verbatim term anchoring: calculations reference quoted agreement text with clause identifiers; a calculation citing a paraphrase fails review.
- Evidence-gated exclusions: no exclusion applies without a linked artifact (pause log, published maintenance window, customer-information request timestamp); unevidenced exclusions default to non-exclusion.
- Dual computation: a second analyst independently recomputes a sample of credits each period, and any variance is resolved before statements are issued.
- Reproduction test: quarterly, a credit is recomputed from the frozen record alone by someone not involved in the original run; matching output is the pass condition.
- Cap ledger: a running ledger per customer tracks cap consumption across periods so accumulation and carry-forward rules are applied against actual history, not memory.

## Validation evidence

The evidence set per period includes: calculation records for each credit event with hashes of frozen exports; the exclusion log with evidence links and rejection of unevidenced claims; dual-computation sample results and variance resolutions; the quarterly reproduction test report; the cap ledger; and copies of issued statements with delivery confirmations. Where a customer disputes a credit, the dispute is answered with the calculation record, and the resolution (upheld, corrected, or clarified) is written back into the term-extraction notes so the next calculation inherits the clarified interpretation.

## Failure modes and correction

The silent exclusion is the most damaging failure: a customer-delay pause is applied without evidence, the breach disappears, and no credit is issued. Correction: evidence-gated exclusions with default-to-non-exclusion, plus the dual-computation sample that specifically re-verifies exclusion artifacts.

Clock ambiguity is second: the agreement does not state business-hours boundaries or timezone, and the system quietly uses the vendor's local calendar. Correction: the favorable-to-customer rule, recorded interpretation, and contract clarification; historical marginal cases are recomputed and credited if the customer's reading prevails.

Fee-base error is third: the percentage is right but applied to the wrong subscription or the wrong period's fees. Correction: the computation step names its fee base explicitly, and the dual computation verifies base and period, not only arithmetic.

Statement opacity is fourth: the credit amount arrives with no derivation, disputes escalate, and trust erodes. Correction: the full-derivation statement format above, which converts disputes into reference checks.

## Limitations

The discipline depends on the agreement being computable; terms like "commercially reasonable efforts" produce no arithmetic and must be renegotiated, not calculated. Timestamp integrity limits everything: a telephony clock skewed from the ticketing clock creates disputes no worksheet can settle, so clock synchronization is a prerequisite investment. Credits computed on estimated fee bases (usage-based billing not yet finalized) are provisional and must be labeled as such. Finally, retroactive term changes (renewals with new schedules) require period-boundary care so no case is calculated under a mixture of two agreement versions.

## Canonical sources

- NIST SP 800-53 Rev. 5, System and Services Acquisition control family, https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- NIST SP 800-137, Information Security Continuous Monitoring (ISCM) for Federal Information Systems and Organizations, https://csrc.nist.gov/pubs/sp/800/137/final
- IETF RFC 3339, Date and Time on the Internet: Timestamps, https://www.rfc-editor.org/rfc/rfc3339.html
