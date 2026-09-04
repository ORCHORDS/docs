# Retained Internet Exposure Hardening Review

## Trigger
Run before approving a public exposure, after major upgrades or architecture changes, after a support-status change, and during recurring internet-attack-surface review.

## Inputs
- List of internet-accessible assets/services that have a current operational need.
- Current software/firmware versions and supplier support state.
- Remote-access architecture and authentication controls.
- Ingress/egress monitoring and alerting coverage.
- Applicable port/protocol exposure information.

## Procedure
1. Confirm each reviewed asset still has a current reason to remain internet-accessible.
2. Verify manufacturer/vendor default credentials are not in use and any bootstrap credentials are handled according to the approved model.
3. Verify current applicable security updates are installed or that any patch gap has a documented owner and remediation date.
4. Confirm the product/device remains in security support; if support has ended, open a removal, replacement, or upgrade action.
5. Restrict remote administrative access through a jump host, VPN, policy-enforcement point, or other controlled path when appropriate to the architecture.
6. Verify MFA is applied to remote access where supported and appropriate, including at the controlled access path when direct device support is limited.
7. Minimize exposed ports, protocols, services, and management functions to those actually required.
8. Verify ingress and egress monitoring can identify anomalous activity requiring investigation.
9. Test IPv4 and IPv6 exposure where either protocol is enabled.
10. Perform external validation that the resulting attack surface matches the approved design.
11. Record exceptions with owners and review/expiry dates, then schedule the next routine assessment.

## Escalation
Escalate unsupported technology, default credentials, unexplained administrative exposure, critical patch gaps, or required public services that cannot be monitored or access-controlled to the expected level.

## Evidence
- Current necessity decision.
- Patch/support-state evidence.
- Authentication and controlled-access test.
- Port/protocol exposure scan.
- Monitoring test.
- External validation result.
- Exceptions and follow-up dates.

## Completion criteria
Every retained public exposure is necessary, supported, patched or actively remediating gaps, access-controlled, monitored, and externally verified against the approved attack surface.

## Source basis
- CISA, Internet Exposure Reduction Guidance, published June 4, 2025: https://www.cisa.gov/resources-tools/resources/exposure-reduction
- CISA, BOD 23-02 background on internet-exposed management interfaces: https://www.cisa.gov/news-events/alerts/2023/06/13/cisa-issues-bod-23-02-mitigating-risk-internet-exposed-management-interfaces
