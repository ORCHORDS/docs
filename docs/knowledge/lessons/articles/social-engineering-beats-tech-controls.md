# social-engineering-beats-tech-controls

**Issue:** Technically sophisticated security controls fail when attackers bypass them by manipulating people
**Date:** 2026-08-11
**Status:** documented

## What happened
A company had MFA, IP allowlisting, and encrypted secrets. An attacker called the IT helpdesk posing as a senior engineer locked out of their account during a critical incident. Under pressure, the helpdesk agent reset MFA without following the identity verification procedure. The attacker gained full access in 20 minutes. None of the technical controls were relevant.

## The lesson
Social engineering attacks target the human layer, not the technical layer. Security training must include realistic simulations of phone-based, email-based, and in-person social engineering. Procedures for sensitive actions (MFA reset, account recovery) must be written, drilled, and enforced — not left to individual judgment under pressure.

## Why it matters
The most hardened technical perimeter is irrelevant if an attacker can talk their way past it. Most major data breaches in recent years involved social engineering as an entry vector.

## How to apply
- [ ] Require written identity verification procedures for any account recovery or MFA reset — no exceptions, no urgency overrides.
- [ ] Run social engineering simulations (phone vishing, in-person tailgating) as part of your security training program.
- [ ] Train staff to say "I need to follow our procedure" and hang up/escalate when under pressure.
- [ ] Require a second human to approve any sensitive account action (MFA reset, privilege escalation).
- [ ] Debrief any social engineering attempt (real or simulated) with the full team.

## Related
- `phishing-simulation-before-incident.md`
- `insider-threat-is-real.md`
- `two-person-rule-for-production-access.md`
