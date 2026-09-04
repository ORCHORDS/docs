# Secure Network Management Protocol Review

## Trigger
Run before device deployment, after firmware/OS or management-service changes, after AAA/logging changes, and during periodic network-infrastructure hardening review.

## Inputs
- Network-device management-service inventory.
- Approved management protocol baseline.
- Management ACL/policy configuration.
- Central AAA and logging architecture.
- Emergency/local account policy.

## Procedure
1. Enumerate every enabled management, file-transfer, discovery, monitoring, and remote-administration protocol on the devices in scope.
2. Identify services that are not operationally required and disable or restrict them according to the approved baseline.
3. Verify routine administration uses encrypted and authenticated protocols such as SSH, HTTPS, SFTP/SCP, or another approved secure alternative.
4. Verify plaintext management alternatives such as Telnet, FTP, or unencrypted HTTP are disabled unless an explicit, time-bounded exception exists.
5. Where SNMP is required, verify an authenticated/encrypted configuration such as SNMPv3 and restrict permitted managers/sources.
6. Confirm management protocols are allowlisted to approved administrative sources rather than broadly reachable.
7. Test centralized AAA for routine administrative login, authorization, and accounting where supported.
8. Review emergency/local administrator accounts separately for limited use, protection, and auditability.
9. Trigger successful and failed management authentication and verify relevant events arrive in protected centralized logging.
10. Test an unapproved source and confirm the management policy denies the attempt and produces evidence where supported.
11. Record weak or unused protocols, AAA gaps, logging gaps, and remediation; retest after changes.

## Escalation
Escalate reachable plaintext administrative protocols, missing restrictions on privileged management services, unexplained local-only administration, or failure to record security-relevant management activity.

## Evidence
- Enabled-service inventory.
- Secure/plaintext protocol test results.
- SNMP security configuration evidence where applicable.
- ACL/allowlist negative tests.
- AAA authentication/accounting evidence.
- Central logging receipt evidence.
- Findings and retest results.

## Completion criteria
Only required, approved management protocols remain reachable from approved sources, with centralized identity/accounting and protected logging applied where the platform supports them.

## Source basis
- CISA, Enhanced Visibility and Hardening Guidance for Communications Infrastructure: https://www.cisa.gov/resources-tools/resources/enhanced-visibility-and-hardening-guidance-communications-infrastructure
- CISA Joint Cybersecurity Advisory AA25-239A: https://www.cisa.gov/news-events/cybersecurity-advisories/aa25-239a
