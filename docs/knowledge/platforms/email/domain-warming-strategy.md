# domain-warming-strategy

**Issue:** Building sending reputation for a new or previously cold sending domain
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Even on a warm shared IP, a brand-new domain gets junked because the domain itself has no reputation history with ISPs.

## Pattern / Solution
Domain reputation is tracked separately from IP reputation. Follow the same volume ramp as IP warming but focused on domain signals.

Steps:
1. Authenticate fully — SPF, DKIM, DMARC (p=none to start) before sending a single message
2. Send from a consistent `From:` address (e.g., `hello@newdomain.com` not rotating addresses)
3. Start with your best audience: users who explicitly requested mail, recent sign-ups
4. Use a subdomain for marketing (e.g., `mail.yourdomain.com`) to isolate reputation from transactional mail

Subdomain strategy:
```
transactional: noreply@yourdomain.com (SPF/DKIM aligned on yourdomain.com)
marketing:     hi@mail.yourdomain.com (SPF/DKIM aligned on mail.yourdomain.com)
```
This prevents a marketing spike or complaint burst from contaminating transactional delivery.

Monitor:
- Google Postmaster Tools shows domain-level reputation separately from IP reputation
- Aim for "High" domain reputation before scaling volume

## Gotchas
- Domain age matters; a domain registered yesterday with no web presence gets extra scrutiny
- Building a web presence (live website, Google index, MX records) before sending helps
- DMARC `p=none` is fine to start; upgrade to `p=quarantine` after 2–4 weeks of clean data

## Related
- `ip-warming-strategy.md`
- `spf-record-setup.md`
- `google-postmaster-setup.md`
