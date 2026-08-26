# email-authentication-check-tools

**Issue:** Tools for verifying SPF, DKIM, DMARC, and overall email deliverability setup
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
After configuring email authentication, you need to verify records are correct and alignment is working.

## Pattern / Solution
Recommended tools:
| Tool | Use |
|---|---|
| MXToolbox (mxtoolbox.com) | SPF, DKIM, DMARC, MX lookup |
| mail-tester.com | Send a test email, get spam score |
| DMARC Analyzer | Visualize DMARC reports |
| Google Postmaster Tools | Gmail reputation and authentication |
| Microsoft SNDS | Outlook/Hotmail reputation |
| dmarcian | DMARC report parsing and management |
| learndmarc.com | DMARC record validator |

CLI: `dig TXT yourdomain.com` for SPF, `dig TXT selector._domainkey.yourdomain.com` for DKIM.

## Gotchas
- DNS propagation takes up to 48 hours; wait before assuming a record is wrong.
- DKIM selector must match what the ESP configured; check ESP dashboard for selector name.
- DMARC reports take 24 hours to start appearing after enabling.

## Related
- spf-record-setup, dkim-record-setup, dmarc-policy-setup, postmaster-tools-setup
