# CIS Critical Security Controls v8 Mapping Adoption Playbook

## Purpose

Establish and maintain the ORCHORDS Security Control Matrix (SCM) that maps CIS Critical Security Controls v8 safeguards to existing policies, tooling, and controls so that auditors and security engineers can demonstrate coverage.

## Audience

Security engineering, GRC analysts, internal audit, control owners across IT and engineering.

## Pre-conditions

- Approved CIS CSC v8 governance card (see `CIS_CSC_V8_GOVERNANCE.md`).
- Access to the existing NIST CSF and ISO 27001 control matrices.
- Inventory of implemented controls across identity, network, endpoint, application, and data domains.
- A shared spreadsheet or GRC platform with read/write access for control owners.

## Procedure

1. **Import the v8 safeguards**: load all 153 safeguards into the SCM template. Tag each with the relevant Implementation Group (IG1/IG2/IG3) and primary control family.
2. **Assign ownership**: route each of the 18 control families to the responsible team. Confirm or update the existing owner list.
3. **Map to existing controls**: for every safeguard, link to one or more existing controls (e.g. CIS CSC 5.4 maps to IAM short-lived token policy + AWS IAM access analyzer).
4. **Mark coverage status**: classify each safeguard as Implemented, Partially Implemented, Planned, Not Applicable, or Compensating.
5. **Identify gaps**: any Partially Implemented or Planned safeguard triggers a remediation ticket with a 90-day SLA (or longer if accepted by exception).
6. **Cross-reference NIST CSF and ISO 27001**: complete the cross-walk columns in the SCM. This drives the controls → risk traceability required by both frameworks.
7. **Evidence collection**: for each Implemented safeguard, capture evidence (config snapshot, policy link, runbook reference) into the SCM.
8. **Review**: weekly SCM review with control owners; monthly review with the CISO; quarterly report to the Risk Committee.
9. **Audit prep**: at audit time, export the SCM with evidence attachments to the auditor's workspace.

## Rollback

- If a major version of CIS CSC ships (e.g. v9), do not delete v8 — retain for historical reporting.
- Re-baseline the SCM under a new sheet named after the new version. Reference both in audit deliverables.
- Treat the swap as a normal quarterly update; no operational rollback needed because SCM is documentation only.

## References

- CIS Critical Security Controls v8 — https://www.cisecurity.org/controls/v8
- Internal reference card: `CIS_CSC_V8_GOVERNANCE.md`.
- Internal NIST IR 8286 cyber-to-enterprise risk governance card.
