# Change Control Record Template

Use this record to document a configuration-controlled change from proposal through approval, testing, implementation, and review. NIST SP 800-53 Rev. 5 CM-3 requires organizations to document, review, approve, test, validate, and retain records of configuration-controlled changes.

## Change identification
- **Change ID:** <identifier>
- **System or service:** <system-or-service>
- **Owner:** <role>
- **Requested date:** <date-time>
- **Planned implementation:** <date-time>

## Proposal and justification
- **Summary:** <change-summary>
- **Business or technical reason:** <reason>
- **Affected components:** <components>
- **Dependencies:** <dependencies>
- **Security or privacy impact:** <impact-summary>

## Risk and rollback
- **Risk level:** <low-medium-high>
- **Primary failure modes:** <failure-modes>
- **Rollback trigger:** <trigger>
- **Rollback procedure:** <procedure-or-reference>

## Pre-implementation evidence
| Gate | Result | Evidence |
| --- | --- | --- |
| Review completed | <yes-no> | <reference> |
| Required tests passed | <yes-no> | <reference> |
| Security impact reviewed | <yes-no> | <reference> |
| Approval received | <yes-no> | <reference> |

## Implementation
- **Implemented by:** <role>
- **Start time:** <date-time>
- **Completion time:** <date-time>
- **Observed deviations:** <none-or-details>

## Post-change validation
- **Service health verified:** <yes-no>
- **Security controls rechecked:** <yes-no>
- **Rollback required:** <yes-no>
- **Validation evidence:** <reference>

## Completion criteria
Close the change only after required approval, testing, implementation evidence, and post-change validation are recorded.

## Reference basis
- NIST SP 800-53 Rev. 5, CM-3 Configuration Change Control: https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
