# Change Control Playbook

## Trigger

Use before implementing a configuration-controlled change to production systems, infrastructure, security settings, operational procedures, or other managed components.

## Inputs

- proposed change and justification;
- affected systems, dependencies, and owners;
- security and privacy impact information;
- test plan and rollback procedure;
- required approvals and maintenance window.

## Steps

1. **Define the change.** Record the exact intended modification, affected components, owner, and reason for change.
2. **Assess impact.** Identify operational, security, privacy, dependency, and availability risks before implementation.
3. **Prepare rollback.** Define a known-good state, rollback trigger, and executable recovery procedure.
4. **Test before finalizing.** Validate the change in an appropriate environment or through another controlled method and retain evidence.
5. **Obtain approval.** Do not implement until the designated approval authority has accepted the change and any residual risk.
6. **Implement through the controlled path.** Restrict implementation to authorized personnel and record deviations from the approved plan.
7. **Validate after change.** Confirm expected behavior, service health, and relevant security controls after implementation.
8. **Close or roll back.** Close only when validation succeeds; otherwise execute rollback or open a corrective action.
9. **Retain the record.** Preserve proposal, approval, testing, implementation, and validation evidence according to the applicable retention rule.

## Completion criteria

The change is complete when the approved scope was implemented, post-change validation passed, rollback was not required or was successfully completed, and the change record contains traceable evidence.

## Sources

- NIST SP 800-53 Rev. 5, CM-3 Configuration Change Control: https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- NIST SP 800-53A Rev. 5, CM-03 assessment procedures: https://csrc.nist.gov/pubs/sp/800/53/a/r5/final

## Scope note

This playbook is a generic control workflow, not a substitute for an organization-specific change policy or emergency-change procedure.
