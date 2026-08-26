# ny-dfs-cybersecurity-regulation

**Issue:** New York DFS 23 NYCRR 500 cybersecurity regulation compliance (2023 amendments)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
NY DFS Part 500 applies to licensed financial services companies in New York (banks, insurers, money transmitters). 2023 amendments added CISO requirements, enhanced controls, and annual senior officer certification.

## Pattern / Solution
2023 amendments — new or enhanced requirements:

Annual certification (Section 500.17(b)):
- Senior officers or board must certify compliance by April 15 each year
- Covers prior calendar year compliance
- Knowing false certification = significant personal liability

CISO requirements:
- Must report to board or equivalent at least annually on cybersecurity posture
- Must have adequate authority and resources
- Can be shared service; must be qualified

Enhanced technical controls (all covered entities):
- MFA required for all remote access and privileged accounts (no exceptions)
- Endpoint detection and response (EDR) required
- Privileged access management (PAM) required
- Vulnerability management: critical vulns remediated within 72 hours of identification
- Web application firewall required for internet-facing apps

Large covered entities (>$20B assets or >500 employees) additional requirements:
- Dedicated CISO
- Independent audit function
- Penetration testing by qualified external party annually
- Vulnerability scanning quarterly

Incident notification:
- Notify DFS within 72 hours of a cybersecurity event with potential to cause material harm
- Notify within 24 hours of a ransom payment

Annual filing (by April 15):
- Certification of compliance
- Acknowledgment of any control deficiencies and remediation plans

## Gotchas
- Regulation applies based on DFS license, not HQ location — non-NY companies with NY licenses must comply
- Third-party service providers must be assessed annually; key controls must be in contracts
- Covered entity is responsible for affiliate access to its systems
- DFS enforcement is active — exam findings can result in consent orders and financial penalties

## Related
- `soc2-cc6-logical-access-controls.md`
- `nist-csf-2-mapping.md`
