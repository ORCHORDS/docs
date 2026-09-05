# Post-Incident Security Architecture Review Playbook

## Purpose

Conduct a structured post-incident review whose primary output is *architecture deltas* — system or control changes that prevent the same class of incident from recurring — rather than just a timeline. The review supplements the standard post-mortem (which focuses on detection, response, and communications) by adding a dedicated architecture track.

## Procedure

1. **Confirm the review window.** Within five business days of incident closure, schedule the architecture review for the same day as the post-mortem so all participants are present.
2. **Reconstruct the attack chain.** Pull:
   - All alerts and detections (SIEM + EDR + cloud audit logs).
   - All responder actions (PagerDuty/incident-management timeline).
   - All relevant SBOMs and config snapshots at the time of the incident.
3. **Map the chain to architectural defences.** For each link in the attack chain, identify:
   - Which control was supposed to stop it (prevention, detection, response).
   - Why the control failed (unconfigured, misconfigured, bypassable, missing).
   - Whether the failure was a control-impairment issue or a missing-control issue.
4. **Generate architecture deltas.** For each identified gap, produce one or more of:
   - A `SECURITY_ARCHITECTURE_REVIEW.md` amendment proposing a new or modified control.
   - A new control mapping (e.g., a NIST 800-53 Rev. 5 / SP 800-207A delta).
   - A `ThreatModel` amendment with the new attack chain.
   - A backlog item with priority, owner, and acceptance criteria.
5. **Decision matrix.** For each proposed delta, decide:
   - **Adopt** — implement by the next release.
   - **Park** — file in security backlog with a review trigger.
   - **Reject** — explicitly reject with a rationale. Rejections are recorded, not silent.
6. **Owner assignment.** Each adopted delta MUST have:
   - A single owner with a date by which implementation begins.
   - A reviewer (different from owner).
   - An acceptance test or measurable success criterion.
7. **Cross-link to operational review.** If the post-mortem identified operational improvements (faster paging, clearer runbook, etc.), these are tracked in `POST_INCIDENT_ACTION_TRACKING.md`. Architecture deltas are tracked in `SECURITY_ARCHITECTURE_REVIEW.md`.
8. **Verify.** After each delta is implemented, the owner MUST demonstrate the change:
   - Reproduce the original incident scenario in a test environment; confirm the new control stops it.
   - Update the runbook that responders used so future responders see the new control in the response flow.
9. **Publish.** Publish the architecture review summary (without sensitive details) to the engineering wiki. Sensitive details (specific CVEs, exploitation details) stay in the secure incident repository.
10. **Cycle.** Treat each architecture review delta as a control improvement that requires its own quarterly review cycle (NIST SP 800-53 CA-7 continuous monitoring) to confirm effectiveness.
