# Access Review Record Template

Use this record to document a periodic account and privilege review. NIST SP 800-53 Rev. 5 AC-2 requires organizations to review accounts for compliance with account-management requirements at an organization-defined frequency.

## Review identification
- **Review period:** <period>
- **System or service:** <system-or-service>
- **Reviewer:** <role>
- **Account owner or manager:** <role>

## Population reviewed
- **Account inventory reference:** <reference>
- **Account types included:** <user-admin-service-shared-other>
- **Privileged accounts separately reviewed:** <yes-no>
- **Temporary or emergency accounts included:** <yes-no>

## Review checks
| Check | Result | Evidence |
| --- | --- | --- |
| Account still required | <pass-fail> | <reference> |
| Owner or user still authorized | <pass-fail> | <reference> |
| Group and role membership appropriate | <pass-fail> | <reference> |
| Privileges remain least necessary | <pass-fail> | <reference> |
| Dormant or stale accounts identified | <pass-fail-not-applicable> | <reference> |
| Shared credentials require rotation | <yes-no-not-applicable> | <reference> |

## Findings and actions
- **Accounts to disable or remove:** <list-or-reference>
- **Privileges to reduce or change:** <list-or-reference>
- **Credential rotations required:** <list-or-reference>
- **Exceptions:** <none-or-reference>
- **Action owner:** <role>
- **Due date:** <date>

## Closure
- **Actions completed:** <yes-no>
- **Residual exceptions approved:** <yes-no-not-applicable>
- **Closure evidence:** <reference>
- **Next review due:** <date>

## Reference basis
- NIST SP 800-53 Rev. 5, AC-2 Account Management: https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
