# bug-bounty-program-setup

**Issue:** Launching and operating a bug bounty program to receive external vulnerability reports responsibly
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Enterprise customers and compliance frameworks (ISO 27001 A.6.8, some SOC 2 CC7.1 interpretations) increasingly expect a coordinated vulnerability disclosure (CVD) or bug bounty program. Without one, researchers who find vulnerabilities either go public immediately or have no safe channel to report — both outcomes are worse than a managed program.

## Pattern / Solution
**Two-tier approach:**

**Tier 1 — Responsible Disclosure Policy (free, immediate):**
Publish a `security.txt` and a disclosure policy before you have a formal bounty program.

```
# /.well-known/security.txt
Contact: mailto:security@example.com
Contact: https://example.com/security
Expires: 2027-01-01T00:00:00Z
Policy: https://example.com/security/disclosure-policy
Preferred-Languages: en
```

Disclosure policy minimum content:
- Where to report (email or form)
- What you will do with the report (triage timeline, fix timeline)
- What you commit to the researcher (no legal action for good-faith research, credit if desired)
- What is out of scope

**Tier 2 — Managed Bug Bounty (HackerOne, Bugcrowd, Intigriti):**

Program structure:
```yaml
program:
  name: "Example Bug Bounty"
  type: "private"   # Start private; invite 20-50 trusted researchers first
  response_sla:
    triage: 5 business days
    bounty_decision: 10 business days

scope:
  in_scope:
    - "*.example.com"
    - "api.example.com"
    - "mobile app (iOS/Android)"
  out_of_scope:
    - "*.staging.example.com"
    - "Third-party services (Stripe, etc.)"
    - "Denial of service"
    - "Social engineering"
    - "Physical attacks"
    - "Clickjacking on pages with no sensitive actions"
    - "Missing security headers with no demonstrable impact"

bounty_table:
  critical (CVSS 9+): $2000–$5000
  high (CVSS 7–8.9):  $500–$2000
  medium (CVSS 4–6.9): $100–$500
  low (CVSS <4):       Swag / acknowledgement
```

**Triage workflow:**
1. Acknowledge receipt within 24 hours.
2. Reproduce the vulnerability within 5 business days.
3. Assign CVSS score; confirm scope eligibility.
4. Fix timeline communicated to reporter; fix deployed.
5. Pay bounty within 10 days of valid triage.
6. Public disclosure: coordinate with researcher; 90-day default embargo.

**Legal safe harbor language (include in policy):**
```
We commit that we will not pursue legal action against researchers who
discover and report security vulnerabilities in accordance with this policy,
provided they do not access data beyond what is necessary to demonstrate
the vulnerability, do not perform destructive testing, and report to us
before public disclosure.
```

## Gotchas
- Launch private first — a public program before your team is operationally ready generates a flood of low-quality reports that overwhelms the queue.
- "No legal action" must be unambiguous; vague language discourages good-faith researchers and attracts those who will go public anyway.
- Out-of-scope items must be precise; "no social engineering" is clear, but "no logic bugs" is not — define what you will and will not pay for.
- Duplicate submissions: a later reporter who found the same bug independently still deserves acknowledgement; decide the policy in advance.
- Bounty amounts must be competitive enough to attract skilled researchers — below-market bounties attract volume reporters submitting known-issues.
- CVSS score alone is not sufficient for bounty calculation — business context matters (e.g., a CVSS 5 tenant isolation bypass may warrant a higher payout).

## Related
- `penetration-testing-scope.md`
- `security-incident-response-plan.md`
- `gdpr-breach-notification-72h.md`
