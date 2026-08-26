# email-from-name-strategy

**Issue:** Choosing from-name and from-address strategy for recognition and deliverability
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
From name is one of the first things recipients see; it drives recognition, trust, and open rates.

## Pattern / Solution
Common patterns:
- **Product name:** `Acme App <noreply@acme.com>` — good for transactional, consistent branding.
- **Person at company:** `Alice from Acme <alice@acme.com>` — higher open rates for outbound/marketing.
- **Team:** `Acme Support <support@acme.com>` — clear for support flows.

Rules:
1. Keep from name consistent; changing it confuses subscribers and hurts recognition.
2. Use a real or monitored reply-to address; `noreply@` frustrates users.
3. From domain must be authenticated with SPF and DKIM.
4. CAN-SPAM requires from address to accurately identify the sender.

## Gotchas
- Different from names for different email types (transactional vs. marketing) are fine; be consistent within type.
- Gmail shows "via sendgrid.net" if DKIM domain doesn't match from domain; align domains.
- Avoid changing from address mid-campaign; preserves deliverability reputation.

## Related
- email-reply-to-patterns, spf-record-setup, dkim-record-setup, can-spam-compliance
