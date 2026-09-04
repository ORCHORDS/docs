# Network Management Protocols Are Security Boundaries

**Issue:** Administrative access is considered protected because it is "internal," while plaintext or weak management protocols, broad management ACLs, and incomplete accounting remain enabled.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

Recent CISA network-hardening guidance tells defenders to use encrypted and authenticated management protocols, disable plaintext alternatives, restrict management services to approved sources, and centralize authentication/authorization/accounting and logging. A management protocol carries privileged control and must be treated as an authorization and evidence boundary, not ordinary internal traffic.

## Engineering rule

- Use approved encrypted/authenticated protocols for administration and file transfer.
- Disable plaintext management protocols and unused discovery/management services unless an exceptional constraint is documented.
- Restrict management protocols with allowlisted/default-deny policy.
- Use centralized AAA for routine administration where the platform supports it; govern emergency local accounts separately.
- Send authentication, authorization, accounting, and relevant management events to protected centralized logging.
- Use authenticated/encrypted SNMP configurations and access restrictions where SNMP is required.

## Verification

- Enumerate enabled management services and confirm no unapproved plaintext protocol is reachable.
- Test an unapproved source against the management ACL/policy and confirm denial is logged.
- Authenticate through the approved AAA path and confirm accounting/log evidence reaches the central system.

## Official sources

- CISA, Enhanced Visibility and Hardening Guidance for Communications Infrastructure: https://www.cisa.gov/resources-tools/resources/enhanced-visibility-and-hardening-guidance-communications-infrastructure
- CISA Joint Cybersecurity Advisory AA25-239A: https://www.cisa.gov/news-events/cybersecurity-advisories/aa25-239a
