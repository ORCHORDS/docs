# Access Review Playbook

## Trigger

Use at the organization-defined review interval and after material personnel, role, ownership, or system changes that may make existing access inappropriate.

## Inputs

- current account inventory;
- account owners or managers;
- role and group memberships;
- privilege assignments;
- personnel status or authorization data;
- approved exceptions.

## Steps

1. **Define the review population.** Include relevant user, privileged, service, shared, temporary, emergency, and other account types.
2. **Confirm ownership and need.** Verify each account still has a valid owner, authorized user, and business or technical purpose.
3. **Review roles and privileges.** Compare group membership and privileges with current responsibilities and intended system use.
4. **Scrutinize privileged access.** Review administrative and other high-impact access separately and require clear justification.
5. **Identify stale access.** Flag dormant, temporary, transferred, terminated, or otherwise unnecessary accounts and permissions.
6. **Handle shared credentials.** When group or shared authenticators exist, determine whether membership changes require credential rotation.
7. **Assign remediation.** Record disablement, removal, privilege reduction, rotation, or exception actions with owners and due dates.
8. **Verify closure.** Confirm remediation was completed and residual exceptions were explicitly approved.
9. **Schedule the next review.** Record the next required review date and preserve the evidence set.

## Completion criteria

The review is complete when the scoped account population has been checked, inappropriate access has a completed or tracked corrective action, exceptions are authorized, and the next review is scheduled.

## Sources

- NIST SP 800-53 Rev. 5, AC-2 Account Management: https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final

## Scope note

The review frequency and authoritative identity source are organization-defined. This playbook does not prescribe a universal interval.
