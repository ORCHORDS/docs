# email-deliverability-fundamentals

**Issue:** Core concepts every sender must understand before optimizing deliverability
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Emails go to spam or are silently dropped despite technically valid configuration.

## Pattern / Solution
Deliverability is determined by three pillars:

**1. Authentication** (proves you are who you say you are)
- SPF, DKIM, DMARC must all pass and align
- Without this, major ISPs may reject or junk mail outright

**2. Reputation** (earned trust with ISPs)
- IP reputation: history of the sending IP address
- Domain reputation: history of the `From:` domain
- Both decay if you send to invalid addresses, generate complaints, or go inactive

**3. Content / Engagement** (signal that recipients want your mail)
- Open rates, click rates, reply rates, move-to-inbox signals build positive reputation
- Spam complaints (marking as junk), deletes-without-open, and unsubscribes degrade it

Key metrics to watch:
| Metric | Warning threshold | Critical threshold |
|--------|------------------|--------------------|
| Bounce rate | > 2% | > 5% |
| Spam complaint rate | > 0.08% | > 0.3% |
| Unsubscribe rate | > 0.5% | > 1% |

## Gotchas
- ISP algorithms are proprietary; there is no single deliverability "fix"
- Sending from a new IP/domain requires a warm-up period even if your list is clean
- Good deliverability requires ongoing maintenance, not a one-time setup

## Related
- `ip-warming-strategy.md`
- `email-reputation-monitoring.md`
- `bounce-handling-hard-soft.md`
- `complaint-rate-monitoring.md`
