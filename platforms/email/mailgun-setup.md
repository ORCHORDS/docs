# mailgun-setup

**Issue:** Setting up Mailgun for transactional and bulk email sending
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams needing flexible SMTP and API sending with robust log access and EU data residency options choose Mailgun.

## Pattern / Solution
1. Create Mailgun account, add and verify domain under Sending > Domains.
2. Add DNS records: SPF (`v=spf1 include:mailgun.org ~all`), DKIM (provided in dashboard), MX for inbound (optional).
3. Send via API:
```bash
curl -s --user 'api:YOUR_API_KEY' \
  https://api.mailgun.net/v3/yourdomain.com/messages \
  -F from='Sender <noreply@yourdomain.com>' \
  -F to='user@example.com' \
  -F subject='Hello' \
  -F text='Hello world'
```
4. Or use SMTP: host `smtp.mailgun.org`, port 587, TLS, credentials from dashboard.
5. Set up webhooks under Sending > Webhooks for bounce/complaint events.

## Gotchas
- EU region uses `api.eu.mailgun.net`; US region uses `api.mailgun.net`. Mismatch causes 404.
- Logs retained 30 days on free plan, longer on paid.
- Sandbox domain is restricted to authorized recipients only.
- Suppression lists are per-domain, not per-account.

## Related
- spf-record-setup, dkim-record-setup, bounce-handling-hard-soft, ses-bounce-complaint-webhooks
