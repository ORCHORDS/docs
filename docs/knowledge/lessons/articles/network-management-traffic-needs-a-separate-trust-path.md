# Network Management Traffic Needs a Separate Trust Path

**Issue:** Routers, switches, firewalls, and other infrastructure devices are administered through the same production or customer-facing paths they are supposed to control.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

CISA's network-hardening guidance recommends isolating device-management traffic from operational data flows, using dedicated out-of-band management or a tightly controlled management network/VRF, and avoiding direct internet administration. The management plane has more authority than ordinary data-plane traffic and should not inherit the same reachability assumptions.

## Engineering rule

- Put network-device administration on a dedicated, enforced management path appropriate to the architecture.
- Do not expose device management directly to the public internet.
- Restrict management sources to approved administrative workstations, jump systems, or management subnets.
- Use default-deny management-plane policy and restrict unnecessary management egress/lateral paths.
- Test both IPv4 and IPv6 reachability when either protocol can carry management traffic.

## Verification

- Attempt management access from an ordinary production/client network and confirm the expected denial.
- Attempt management access from outside the approved administrative path and confirm the expected denial.
- Confirm approved administrative sources can still reach only the management services required by their role.

## Official sources

- CISA, Enhanced Visibility and Hardening Guidance for Communications Infrastructure: https://www.cisa.gov/resources-tools/resources/enhanced-visibility-and-hardening-guidance-communications-infrastructure
- CISA Joint Cybersecurity Advisory AA25-239A: https://www.cisa.gov/news-events/cybersecurity-advisories/aa25-239a
