# rotate-credentials-after-every-breach

**Issue:** Failing to rotate all credentials after a breach leaves attackers with persistent access
**Date:** 2026-08-11
**Status:** documented

## What happened
An API key was exposed in a public GitHub repository. The key was revoked quickly. Two weeks later, the same attacker accessed a secondary service using a different key that had been in the same leaked file but was overlooked during remediation. The partial rotation created a false sense of security while the attack continued.

## The lesson
After any confirmed or suspected credential exposure, rotate every credential that could plausibly have been accessed — not just the one you know was compromised. Treat a breach as an event that may have exposed the entire secret store visible to the compromised process.

## Why it matters
Attackers exfiltrate everything they can see. Rotating one key while leaving others alive gives them a persistent foothold. The cost of over-rotation (updating a few configs) is far lower than the cost of a second breach.

## How to apply
- [ ] After a breach, enumerate every secret accessible to the compromised process/user.
- [ ] Rotate all of them, not just the confirmed-compromised one.
- [ ] Invalidate all active sessions and tokens for affected service accounts.
- [ ] Update all downstream systems that use rotated credentials before invalidating old ones (to avoid downtime).
- [ ] Document what was rotated, when, and by whom — for the post-incident report.
- [ ] Schedule credential rotation proactively every 90 days, not just post-breach.

## Related
- `never-store-secrets-in-env-files.md`
- `two-person-rule-for-production-access.md`
- `supplier-breach-affects-you.md`
