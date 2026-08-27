# Configuration Baseline Review

## Trigger
Run on the defined review cadence, after significant system changes, and when components are installed or upgraded.

## Purpose
Verify that the approved configuration baseline remains current, accurate, and aligned with the deployed state.

## Steps
1. Retrieve the current approved baseline and recent change records.
2. Capture current configuration state using appropriate exports or automated inventory/configuration tooling.
3. Compare current state with the approved baseline.
4. Investigate unexplained or unauthorized deviations.
5. Confirm changes from installations/upgrades were incorporated into the baseline.
6. Remediate unauthorized drift or approve/document justified exceptions.
7. Update the baseline when the approved system state has legitimately changed.
8. Preserve evidence and assign follow-up actions.

## Completion criteria
- Current deployed state has been compared with the approved baseline.
- Deviations have owners and dispositions.
- Required baseline updates are approved and recorded.
- Evidence is retained without secrets.

## Sources
- NIST SP 800-53 Rev. 5, CM-2 Baseline Configuration: https://csrc.nist.gov/projects/risk-management/sp800-53-controls
- NIST SP 800-128: https://csrc.nist.gov/pubs/sp/800/128/final
