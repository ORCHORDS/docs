# Customer Success Risk Acceptance Governance

## Scope and purpose

This risk acceptance practice governs risk acceptance decisions. It applies when the item affects access, adoption, a promised outcome, support, trust, or renewal. It does not replace a contract, specialist security or accessibility assessment, or legal advice. Its purpose is to make an operational decision repeatable and reviewable. The primary reference is NIST SP 800-37 Rev. 2; using it as a design basis does not by itself establish certification, conformance, or legal compliance.

## Control design

The controlled risk acceptance record contains risk, customers, cause, consequence, likelihood basis, controls, alternatives, owner, approver and expiry. The risk owner defines allowed values, review clocks, approval boundaries, exception handling, and evidence retention. These are internal controls, not externally mandated fields.

The controlled record must identify purpose, owner, affected customer tasks, decision criteria, dependencies, exceptions, review date, and evidence for risk acceptance decisions. Give it one accountable owner and named delegates. State entry and exit criteria, review frequency, approval authority, protected information, and escalation thresholds. Dependencies need named owners rather than team labels. Separate verified facts, customer statements, estimates, and assumptions. Material changes require review by someone other than the editor where practical.

Controls should match consequence. High-impact or irreversible decisions need stronger evidence, segregation of duties, and explicit authorization. Automation may route or summarize work, but inputs, thresholds, exceptions, and human override must remain understandable. Collect only information needed for the stated purpose, restrict access, and follow the approved retention schedule.

## Operational workflow

1. Open a dated record from a defined trigger. Identify affected customers, services, requester, urgency, source evidence, and possible duplicate work.
2. Establish context: current customer goal, commitments, baseline, dependencies, communication preference, and any known accessibility need. Never infer need from demographic proxies.
3. Apply documented criteria consistently. Obtain specialist input when privacy, security, safety, accessibility, contractual, or legal boundaries are implicated. Record alternatives and uncertainty.
4. Authorize the decision at the required level. Assign each action, deadline, dependency, and next communication. Transfer only necessary data to downstream systems.
5. Confirm delivery and understanding through a channel the customer can use. Silence alone is not evidence of success; define an observable completion condition.
6. Reconcile actions, exceptions, residual risks, and outcomes. Link defects to improvement work and schedule follow-up where effects are delayed. This review applies that sequence specifically to customer success risk acceptance governance; the owner must tailor thresholds and evidence to that subject.

## Validation evidence

Direct validation must sample approvals, test expiry alerts, challenge scenarios and confirm remediation. Record the sample, environment, expected result, observed result, reviewer, and correction ticket. Reconcile register counts to source systems and include rejected, overdue, and overridden cases so testing cannot pass by examining only clean examples.

To validate operation, test representative cases and reconcile documented risk acceptance decisions decisions with source records, customer-facing behavior, approvals, and exceptions. Retain the criteria version, dated source extracts, approvals, change history, test method and result, sampled communications, exceptions, and corrective actions. Every test record should name the item, reviewer, date, result, and unresolved limitation. Evidence quality matters more than volume.

Review effectiveness as well as procedural completion. Useful indicators include missing evidence, exception age, repeat failure, rework, override frequency, time to verified outcome, and differences by channel. Segment measures enough to reveal systematically excluded users while applying privacy and minimum-sample protections. Internal targets are management choices, not public guarantees unless formally authorized.

## Failure handling

When the control fails, contain customer impact, preserve the decision record, provide a safe alternative, assign correction, and retest the risk acceptance decisions control. Name the containment owner, customer impact, notification decision, next update, recovery deadline, and closure test. Do not close because an internal ticket moved state. Verify the customer-facing condition and search for similarly exposed records or customers. Preserve disputed evidence; never rewrite timestamps or rationale retrospectively.

## Limitations

This practice cannot prove causation, eliminate professional judgment, or repair unreliable source data. Sampling can miss rare harms, lagging measures can reveal defects late, and feedback can contain access and response bias. Standards and local obligations change. A documented control can still fail in use. Reassess after significant change, a material incident, changed source guidance, or evidence that thresholds create unintended outcomes.

## Canonical sources

- https://csrc.nist.gov/pubs/sp/800/30/r1/final
- https://www.coso.org/enterprise-risk-management
