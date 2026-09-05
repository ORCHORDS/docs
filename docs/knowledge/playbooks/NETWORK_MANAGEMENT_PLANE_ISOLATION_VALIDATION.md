# Network Management Plane Isolation Validation

## Trigger
Run before introducing a new network-device class, after management-network or routing changes, after remote-access changes, and during periodic network-infrastructure security review.

## Inputs
- Approved management architecture and source classes.
- Device/service inventory and required administrative protocols.
- Management ACL/policy definitions.
- IPv4/IPv6 reachability information where enabled.
- Approved jump systems, administrative workstations, or management subnets.

## Procedure
1. Enumerate the management interfaces and protocols for the devices in scope.
2. Identify every network/source class that is expected to initiate management traffic.
3. From an approved administrative source, verify only the required management services are reachable.
4. From an ordinary production/client/data-plane source, attempt the same management paths and verify denial.
5. From an external/untrusted source, verify device management is not directly reachable from the public internet.
6. Test lateral management paths between managed devices and confirm only explicitly required flows are permitted.
7. Review management-plane ACLs/policy for default-deny behavior and confirm rejected attempts produce useful logging where supported.
8. Test management egress and confirm it is limited to required infrastructure such as approved AAA, logging, flow, time, or telemetry services.
9. Repeat reachability checks over IPv6 when enabled rather than assuming IPv4 policy provides equivalent coverage.
10. Record gaps, remediate, and rerun the failed source-to-service tests.

## Escalation
Escalate direct internet management, unexpected data-plane-to-management reachability, broad lateral management access, or management paths that cannot be attributed to a documented operational need.

## Evidence
- Source/service reachability matrix.
- Approved-source success tests.
- Unapproved-source negative tests.
- IPv4/IPv6 results where applicable.
- ACL/policy and management-egress evidence.
- Findings and retest evidence.

## Completion criteria
Network-device management is reachable only through the intended management trust path, with unauthorized source classes denied and externally validated.

## Source basis
- CISA, Enhanced Visibility and Hardening Guidance for Communications Infrastructure: https://www.cisa.gov/resources-tools/resources/enhanced-visibility-and-hardening-guidance-communications-infrastructure
- CISA Joint Cybersecurity Advisory AA25-239A: https://www.cisa.gov/news-events/cybersecurity-advisories/aa25-239a
