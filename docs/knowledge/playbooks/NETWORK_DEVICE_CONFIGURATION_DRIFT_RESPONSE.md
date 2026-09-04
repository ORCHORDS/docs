# Network Device Configuration Drift Response

## Trigger
Run when monitoring detects configuration drift, an unauthorized device change, an unexplained route/ACL/user/protocol modification, or a device state that differs from the central intended configuration.

## Inputs
- Central authoritative configuration or intended state.
- Device running/current configuration evidence.
- Change-management records for the relevant period.
- Authentication/accounting and configuration-change logs.
- Known incident or maintenance context.

## Procedure
1. Preserve the current drift evidence before making corrective changes.
2. Compare the device state against the centrally controlled intended configuration and identify the exact differences.
3. Search change-management records to determine whether each difference was approved, emergency-authorized, accidental, or unexplained.
4. Prioritize security-relevant drift involving administrative users, AAA, ACLs, routes, management services, discovery protocols, logging, or weak/unencrypted protocols.
5. If unauthorized activity is suspected, restrict further administrative access as appropriate while preserving required evidence and operational safety.
6. Determine whether the drift changed external exposure, management reachability, routing, or monitoring coverage and validate those effects independently.
7. Restore or reapply the approved configuration through the normal trusted deployment path when safe to do so.
8. Confirm the device converges to the intended state and expected services remain healthy.
9. Confirm drift detection/alerting recognizes the corrected state and can detect a controlled recurrence in a safe test context.
10. Record root cause, responsible change path, detection gap, remediation, and any needed preventive control improvement.

## Escalation
Escalate unexplained privileged changes, evidence of credential misuse, route or ACL manipulation, disabled logging, re-enabled weak management protocols, or recurring drift that bypasses the approved configuration path.

## Evidence
- Preserved before-state/drift evidence.
- Central source-of-truth comparison.
- Change-record correlation.
- Security-impact assessment.
- Restored-state validation.
- Detection/retest evidence.
- Root-cause and preventive actions.

## Completion criteria
The device matches the approved intended state, the cause and authorization status of the drift are understood, security impact is assessed, and the detection/control gap is remediated or explicitly owned.

## Source basis
- CISA, Enhanced Visibility and Hardening Guidance for Communications Infrastructure: https://www.cisa.gov/resources-tools/resources/enhanced-visibility-and-hardening-guidance-communications-infrastructure
