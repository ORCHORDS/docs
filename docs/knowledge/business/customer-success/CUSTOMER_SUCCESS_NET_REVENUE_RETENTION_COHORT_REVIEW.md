# Customer Success Net Revenue Retention Cohort Review

## Scope

This practice structures the periodic review of net revenue retention (NRR) by customer cohort so that the analysis can be compared across cohorts, audited by parties other than the analyst, and reused as input to commercial, financial, and customer success decisions. The framing is the analytics perspective articulated in ISO 22468 on customer retention analytics, and is referenced here as a documented review structure rather than as a binding rule; adopting it does not by itself establish conformance with ISO 22468 and does not substitute for the revenue recognition policy, the financial close process, or the customer's contract. The practice applies whenever NRR is being reviewed for a cohort, segment, region, or product line, and it applies whether the review is monthly, quarterly, or annual.

It does not apply to customer success narratives that are not backed by an underlying extract of customer-level revenue movement, since those narratives are difficult to reconcile against the same data sources and would weaken rather than strengthen the review.

## Workflow or implementation guidance

Open the cohort review by fixing the cohort definition, the period under review, the data source for revenue, the data source for customer identity, and the cut-off date. The cohort definition should be stable across periods, and any change to the definition must be flagged in the same review so that readers can interpret movements correctly. The cut-off date determines which revenue movements count; revenue booked or refunded after the cut-off is excluded, even if it relates to the period under review, and the exclusion must be acknowledged.

Reconcile the cohort's gross retention, gross expansion, gross contraction, and churn against the underlying extract before any analysis. Reconcile the count of customers in the cohort to the source system, and reconcile the count of customers with no revenue in the period to the customer-status field. Reconcile negative movements against the source support records, since a refund or credit can produce an apparent contraction that is not a behavioural signal. Once the cohort is reconciled, compute the movement components, segment the cohort by customer characteristic where the segmentation is meaningful and where the segmentation does not produce segments that are too small to interpret, and write the narrative after the numbers are reconciled, not before.

Authoring notes: separate what the financial system reports, what the customer success system reports, what the customer has stated, and what the analyst is estimating. Where a movement cannot be reconciled within the cut-off, identify the gap and the proposed reconciliation, and do not present the gap as a confirmed figure.

## Controls

The controlled cohort review identifies the cohort definition, the period under review, the data source for revenue, the data source for customer identity, the cut-off date, the reconciliation steps, the reviewer, the reconciliation result, the analyst, and any unresolved gaps. Give it one accountable owner and a named delegate. State the frequency of review, the approval authority for any output that drives revenue recognition or external communication, the data classification, the retention period, and the route for contesting a movement by the customer or by another internal function.

Material changes to the cohort definition require review by someone other than the author before they are reused. Restrict distribution to the audience agreed with the customer and to the internal functions that need it for their own decisions, follow the approved retention schedule, and do not let inferred segmentation produce segments small enough to identify individual customers. Where the review is automated, the inputs, thresholds, and human override must remain understandable.

## Validation evidence

Direct validation must reconcile the cohort's components against the underlying extracts. Record the sample, the data source, the expected result, the observed result, the reviewer, and the correction ticket. Reconcile the cohort count to the source system, reconcile movements to support records, and include rejected, overdue, and overridden cases so testing cannot pass by examining only clean examples.

To validate the review itself, trace a sample of reported movements back to the underlying extracts, and verify that the methodology was applied consistently across periods. Useful indicators of effectiveness include reconciliation gaps that recur without correction, segmentation choices that produce segments too small to interpret, movements that no reviewer can explain to a peer without additional context, and changes in cohort definition that are not flagged. Internal targets are management choices, not public guarantees unless formally authorised.

## Failure modes and correction

When the review fails its own controls, protect the customer and the integrity of the analysis first. If a movement was misclassified, correct the classification in the next review and disclose the correction to anyone who previously relied on the prior classification. If a cohort definition was changed silently, restate the prior period under the new definition or annotate the change clearly so that readers can interpret movements correctly. If a refund or credit was treated as a behavioural signal, remove it from the NRR narrative and treat it as a separate reconciliation item.

When a number proves materially wrong, name the customer impact where one can be named, the reconciliation owner, the next update, the recovery deadline, and the closure test. Do not close because the dashboard moved to a new state. Search for similarly exposed cohorts in the same portfolio, since a single misclassified movement usually signals a wider problem in the underlying extract or in the cohort definition.

## Limitations

This practice cannot prove causation, eliminate professional judgement, or repair unreliable source data. The analytics framing referenced here is a documented review structure, not a binding rule; adopting it does not by itself establish certification, conformance, or legal compliance. Sampling can miss rare harms, lagging measures can reveal defects late, and revenue movements can be driven by events the customer success function did not anticipate, such as a corporate restructuring at the customer.

A documented cohort review can still fail in use. The review is a structure, not a substitute for source-system quality, financial discipline, or judgement. Treat it as a starting point, and reassess after a material incident, a change in the source system, or evidence that the current shape creates unintended outcomes.

## Canonical sources

- https://www.iso.org/standard/62085.html
- https://www.aicpa-cima.com/topic/audit-assurance/audit-and-assurance-greater-than-soc-1