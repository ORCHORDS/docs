# NIST SP 800-61r3 incident response and CSF 2.0 integration

**Issue:** Incident response is operated as a separate, linear runbook, so lessons, owners, evidence, and recovery improvements do not feed back into enterprise risk management.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Symptom

Teams can declare an incident closed but cannot show which control failed, who owns the improvement, whether recovery restored the intended service, or whether the same exposure is being measured and exercised afterward.

## Root cause

NIST SP 800-61r3 supersedes Revision 2 and frames incident response as capabilities integrated throughout cybersecurity risk management and the NIST Cybersecurity Framework 2.0, rather than an isolated sequence that begins only after detection.

**Source:** [NIST SP 800-61r3](https://doi.org/10.6028/NIST.SP.800-61r3).

## Fix

Build an incident-response operating model that connects prevention, detection, response, recovery, and improvement:

- define accountable owners, decision authorities, and evidence locations before an incident;
- map detection, triage, containment, communications, recovery, and lessons-learned outputs to the organization’s CSF risk-management outcomes;
- maintain a risk register link for each material incident: affected asset/service, threat scenario, control gap, risk owner, treatment, due date, and verification evidence;
- preserve event timelines and decisions with integrity controls, access limits, and retention rules;
- rehearse technical and business recovery separately; recovery is not complete merely because a process restarted;
- convert lessons into owned, testable engineering or governance changes and verify their effectiveness in a later exercise or review;
- measure response performance without turning targets into incentives to under-classify incidents.

## Verification

- **Readiness:** an exercise can identify the incident commander, legal/comms contacts, evidence stores, and recovery owner without ad hoc discovery.
- **Traceability:** a material incident has a durable link from event evidence to risk decision, remediation owner, and closure verification.
- **Recovery:** tests demonstrate service, data integrity, access controls, and monitoring are restored to the required state.
- **Improvement:** every accepted residual risk or deferred corrective action has an approver, expiry/review date, and re-evaluation trigger.
- **Exercise:** a scenario that crosses technical and business boundaries produces actionable improvements, not only a retrospective document.

## Gotchas

- CSF mapping does not replace incident-specific playbooks; it makes their governance and feedback loop explicit.
- Do not use a single mean-time metric as proof of response quality. Severity, detection source, scope, data integrity, and recurrence matter.
- Preserve privacy and legal-hold requirements when collecting incident evidence.
- An incident that ends in a vendor or customer action can still reveal an internal control or resilience gap.

## Related

- `lessons/nist-incident-response.md`
- `monitoring/slo-error-budget.md`
- `patterns/incident-management.md`
- `security/security-incident-response-plan.md`
