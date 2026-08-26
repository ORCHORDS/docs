# postmaster-tools-setup

**Issue:** Configuring email postmaster tools to monitor sender reputation
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Google and Microsoft both provide postmaster tools that give insight into how their mail systems view your sending reputation.

## Pattern / Solution
See google-postmaster-setup and microsoft-snds-setup for provider-specific steps.

General approach:
1. Verify sending domain at each postmaster portal.
2. Add monitoring for: domain reputation, IP reputation, spam rate, authentication pass rates.
3. Set up alerts when reputation drops from High to Medium or below.
4. Check weekly as a deliverability health routine.

Combined monitoring schedule:
- Google Postmaster: check weekly, alert if spam rate > 0.1%.
- Microsoft SNDS: check monthly or after complaint spike.
- Senderscore.org: check sending IPs monthly.
- MXToolbox Blacklist Monitor: continuous (paid) or weekly manual check.

## Gotchas
- Postmaster tools only report on mail delivered to that provider's users; may miss other providers.
- Data appears with 1-2 day lag; postmaster tools are not real-time.
- Low volume to a provider (< a few hundred/day) may show "not enough data".

## Related
- google-postmaster-setup, microsoft-snds-setup, email-deliverability-audit, email-reputation-monitoring
