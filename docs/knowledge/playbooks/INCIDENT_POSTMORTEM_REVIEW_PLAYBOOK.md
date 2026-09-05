# Incident Postmortem Architectural Review Playbook

## Purpose

Provide a reproducible procedure for performing an architectural review
after a production incident so that lessons learned are converted into
control updates, detection improvements, and architectural decisions that
are tracked to closure. This complements the operational incident
review; this playbook is specifically about the architectural and
control-surface implications that the on-call postmortem may not cover.

## Audience

Platform architects, security architects, and engineering leads who own
the architectural decisions under review.

## Pre-conditions

- The incident postmortem has been written in the standard template
  and circulated.
- A neutral facilitator has been identified who is not directly
  accountable for the system under review.
- The set of architectural decisions that contributed to or failed to
  prevent the incident is captured in the postmortem.

## Procedure

1. **Schedule the architectural review.** Target within 14 days of
   incident closure so memory is fresh and remediation is not yet
   complete. Invite the system owner, security architect, the
   on-call lead from the incident, and one engineer who has not
   previously worked on the system.
2. **Restate the architectural decision history.** For each component
   that failed or amplified the incident, document the design
   decision, the date it was made, the alternatives that were
   considered, and the rationale for the chosen approach.
3. **Classify contributing decisions.** For each architectural
   decision that contributed to the incident, classify it as one of:
   - **Root cause** — the decision directly enabled the failure.
   - **Amplifier** — the decision did not cause the failure but
     increased its blast radius.
   - **Missed defence** — the decision prevented an existing defence
     from being effective.
   - **Latent risk** — the decision created a risk that was not yet
     realised but should be addressed.
4. **Identify control-surface implications.** For each classification,
   list the controls (preventive, detective, recovery) that should have
   applied, and document why they did not. Include detection coverage,
   alert routing, runbook coverage, and human execution.
5. **Decide remediation actions.** For each implication, write a
   remediation action with:
   - Owner (named individual).
   - Due date (specific date, not a relative phrase).
   - Acceptance criteria (a test or evidence that closes the action).
   - Classification (preventive / detective / recovery).
6. **Cross-link to standards and runbooks.** For every action, identify
   the existing standard or runbook that should govern the work, or
   capture a new standard gap as a follow-up task.
7. **Capture the architectural decision record.** Write a short ADR
   (Architecture Decision Record) that summarises the decision, the
   alternatives, the rationale, the trade-offs, and the date the
   decision was made. Store the ADR with the postmortem so future
   reviewers can trace the lineage.
8. **Report out.** The facilitator writes a one-page summary that the
   engineering organisation can read in two minutes. The summary must
   answer: what was the architectural decision, what was the impact,
   what is being changed, and how will the change be verified.
9. **Track closure.** Each remediation action is tracked in the issue
   tracker of record and reviewed in the next architectural review for
   the affected system. Actions that have a security implication are
   also tracked in the security findings tracker.
10. **Refresh risk register.** Add the architectural risk to the
    system risk register with an owner and a review cadence. If the
    risk cannot be remediated within 90 days, document the risk
    acceptance and the compensating control.

## Patterns to watch for

- **Single point of failure that was documented but accepted.** The
  review MUST surface whether the acceptance was justified at the
  time and whether the conditions that justified it still hold.
- **Implicit coupling.** Architectural decisions that assume a coupling
  between systems (e.g., "deployments always pause during incident
  response") but do not enforce it are frequent amplifiers.
- **Detection debt.** Missing detection is itself an architectural
  decision; surface it explicitly rather than treating it as an
  operational gap.
- **Tooling drift.** Tools that are described as authoritative in the
  architecture documents but have drifted from current behaviour must
  be flagged for re-alignment.
- **Talent and on-call distribution.** Architectural decisions that
  require specialist knowledge from a single individual are a
  structural risk.

## Outputs

The architectural review produces:

- The list of contributing decisions and their classification.
- A set of remediation actions, each with owner, due date, acceptance
  criteria, and classification.
- An updated risk register entry.
- One ADR per contributing decision.
- A two-minute summary for the engineering organisation.

## References

- NIST SP 800-61 Rev. 2 — Computer Security Incident Handling Guide
- NIST SP 800-30 Rev. 1 — Risk Assessment
- TOGAF Architecture Development Method
- AWS Well-Architected Operational Excellence and Security pillars
- Google SRE Book, Chapter on Postmortem Culture
