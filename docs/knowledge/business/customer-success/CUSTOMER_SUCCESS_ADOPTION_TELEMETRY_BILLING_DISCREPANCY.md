# Customer Success Adoption Telemetry Billing Discrepancy

## Scope

This practice structures the investigation of a discrepancy between adoption telemetry and billed usage so that the investigation can be replayed, defended to the customer, and used to drive a measurable improvement in either the telemetry, the billing extract, or both. The framing is the data-minimisation perspective articulated in ISO/IEC 27018 on the protection of personally identifiable information in public clouds acting as PII processors, and is referenced here as a documented structure rather than as a binding rule; adopting it does not by itself establish conformance with ISO/IEC 27018 and does not replace the customer's contract, the supplier's revenue recognition policy, or any specialist privacy, legal, or accounting advice. The practice applies whenever adoption telemetry and billed usage diverge beyond an agreed tolerance, and applies whether the divergence is a count, a volume, a frequency, or a categorical mismatch.

It does not apply to privacy incidents that originate entirely outside the telemetry-billing reconciliation, where the privacy response must be governed by the supplier's incident-response policy rather than by this reconciliation practice.

## Workflow or implementation guidance

Open the investigation by fixing the customer's identifier, the period under review, the source of the adoption telemetry, the source of the billed usage, the agreed tolerance, the cut-off date, and the data minimisation rules that apply to the reconciliation. Pull the relevant extracts from both sources, identify the date and time at which each extract was generated, and confirm that each extract is the version the customer would have seen. Reconcile the extracts against each other before any narrative is written; the reconciliation must include the count of records on each side, the count of records that match on a defined key, the count that match after a known data-cleaning step, and the count that remain unmatched after both.

Sequence the investigation so that the data minimisation rule applies at each step. The investigator should not need to handle more personal data than is needed for the reconciliation, and any personal data that is held during the investigation must be governed by the same retention and access rules that apply to the underlying systems. Where the investigation requires identifying an individual end user, the rule is to use the smallest set of identifiers that resolves the discrepancy, and to record why that set was necessary. Close the investigation with a documented outcome, an action that is anchored to a named owner and a deadline, and a route for telling the customer what the reconciliation found.

Authoring notes: separate what the telemetry reports, what the billing extract reports, what the customer has stated about their own usage, and what the investigator is estimating. Where the reconciliation depends on a data-cleaning step that changes the outcome, document the step before it is applied so that the customer can replay it.

## Controls

The controlled investigation identifies the customer's identifier, the period, the two source extracts, the reconciliation steps, the data minimisation rule, the reviewer, the outcome, the action, the owner, the deadline, and the route for telling the customer. Give it one accountable owner and a named delegate. State the frequency of reconciliation, the approval authority for any change that affects billing, the data classification of every attached exhibit, the retention period, and the escalation route when the customer contests the outcome.

Material changes to the reconciliation steps require review by someone other than the author before they are reused, particularly where the change affects a customer's bill or an audit trail. Restrict distribution to the audience agreed with the customer and to the supplier's billing function, follow the approved retention schedule, and do not let informal adjustments become the de facto resolution without being recorded. Where the reconciliation is automated, the inputs, thresholds, and human override must remain understandable.

## Validation evidence

Direct validation must reconcile a sample of investigations against the source extracts, the reconciliation steps, and the data minimisation rule. Record the sample, the source, the expected result, the observed result, the reviewer, and the correction ticket. Reconcile the investigation count against the upstream discrepancy detector and include rejected, overdue, and overridden cases so testing cannot pass by examining only clean examples.

To validate the practice itself, trace a sample of investigations back to the actions they triggered and verify that the customer's bill, the supplier's billing extract, and the customer's own usage converged after the action. Useful indicators of effectiveness include the lag between detection and resolution, the proportion of investigations closed by a data-cleaning step rather than by a billing change, the proportion of investigations where the data minimisation rule is documented before the reconciliation, and the proportion of investigations that the customer disputes after the fact. Internal targets are management choices, not public guarantees unless formally authorised.

## Failure modes and correction

When the practice fails its own controls, protect the customer's position and the integrity of the supplier's billing first. If a reconciliation step has been applied after the fact, surface the step in the next investigation and re-issue the outcome if the step is material. If a customer's bill has been issued against a reconciliation that did not apply the data minimisation rule, treat the over-handling of personal data as a privacy event and route it through the supplier's incident-response policy. If the customer disputes the outcome, preserve the disputed record and do not rewrite history.

When an investigation proves materially wrong after the fact, name the customer impact, the billing impact, the reconciliation owner, the next update, the recovery deadline, and the closure test. Do not close because an internal ticket moved state. Search for similarly exposed customers in the same portfolio, since a single source of error usually signals a wider problem in the underlying extract. Where the failure relates to data classification or distribution, treat the disclosure channel as the affected control.

## Limitations

This practice cannot prove causation, eliminate professional judgement, or repair unreliable source data. The ISO/IEC 27018 framing referenced here is a documented structure, not a binding rule; adopting it does not by itself establish certification, conformance, or legal compliance. Sampling can miss rare harms, lagging measures can reveal defects late, and the customer's own usage can drift between the telemetry snapshot and the bill.

A documented investigation can still fail in use. The investigation is a structure, not a substitute for source-system quality, financial discipline, or judgement. Treat it as a starting point, and reassess after a material incident, a change in the customer's environment, or evidence that the current shape creates unintended outcomes.

## Canonical sources

- https://www.iso.org/standard/76559.html
- https://www.aicpa-cima.com/topic/audit-assurance/audit-and-assurance-greater-than-soc-1