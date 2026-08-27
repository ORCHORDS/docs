# Backup Restore Test Record Template

Use this record to document a controlled restore test. CISA's #StopRansomware guidance recommends maintaining offline encrypted backups and regularly testing their availability and integrity in disaster-recovery scenarios.

## Test identification
- **Test ID:** <test-id>
- **Date:** <date>
- **Backup set:** <generic-backup-description>
- **Test owner:** <role>
- **Recovery target:** <test-environment>

## Preconditions
- **Backup age:** <age>
- **Backup integrity check:** <result>
- **Recovery environment isolated:** <yes-no>
- **Required credentials/access available:** <yes-no>

## Restore execution
| Step | Result | Evidence |
| --- | --- | --- |
| Retrieve backup | <pass-fail> | <reference> |
| Restore data/system | <pass-fail> | <reference> |
| Validate integrity | <pass-fail> | <reference> |
| Validate application/service | <pass-fail> | <reference> |

## Recovery objectives
- **Observed recovery time:** <duration>
- **Target recovery time:** <duration>
- **Observed data-loss window:** <duration>
- **Target data-loss window:** <duration>

## Findings
- **Failures or gaps:** <findings>
- **Corrective actions:** <actions>
- **Owner:** <role>
- **Due date:** <date>

## Completion criteria
Close only when the restore is validated, integrity is confirmed, recovery objectives are compared with targets, and corrective actions are assigned.

## Reference basis
- CISA — #StopRansomware Guide: https://www.cisa.gov/stopransomware/ransomware-guide
