# spf-record-setup

**Issue:** How to create and publish an SPF TXT record for a sending domain
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Emails from your domain land in spam or fail authentication checks because receiving servers cannot verify that your mail server is authorized to send on behalf of your domain.

## Pattern / Solution
Add a TXT record to your domain's DNS:

```
v=spf1 include:sendgrid.net include:amazonses.com ip4:203.0.113.10 ~all
```

Breakdown:
- `v=spf1` — SPF version identifier (required)
- `include:` — authorizes a third-party sender's IP ranges
- `ip4:` — explicitly authorizes a single IP or CIDR block
- `~all` — softfail (preferred over `-all` while warming; switch to `-all` once stable)

Verify with:
```bash
dig TXT yourdomain.com | grep spf
# or
nslookup -type=TXT yourdomain.com
```

## Gotchas
- DNS has a 10 DNS lookup limit per SPF evaluation; `include:` statements each count as one lookup
- Exceeding 10 lookups causes a PermError, which many receivers treat as fail
- Flattening SPF (replacing `include:` with raw IPs) avoids the limit but breaks when the provider changes IPs
- Only one SPF TXT record is allowed per domain; merge multiple into a single record
- SPF only covers the envelope `MAIL FROM`, not the `From:` header visible to recipients

## Related
- `dkim-record-setup.md`
- `dmarc-policy-setup.md`
- `email-authentication-check-tools.md`
