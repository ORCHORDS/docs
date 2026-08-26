# transactional-vs-marketing-email

**Issue:** Understanding the distinction between transactional and marketing email and why it matters
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams mix transactional and marketing content in the same send stream, causing deliverability and compliance issues.

## Pattern / Solution
**Transactional email** — triggered by a specific user action; content is expected by the recipient:
- Password reset, email verification
- Order confirmation, shipping notification
- Invoice, receipt
- Security alert (new login, 2FA code)

**Marketing / commercial email** — sent to promote products or services; not triggered by a user action:
- Newsletters, product updates
- Promotional campaigns, discount codes
- Re-engagement, win-back sequences
- Drip campaigns

Why separation matters:
1. **Deliverability** — mixing commercial content into transactional streams causes ISPs to treat all mail from that stream as marketing, subject to bulk filtering
2. **Compliance** — transactional email is exempt from CAN-SPAM opt-in/opt-out requirements; marketing is not
3. **User trust** — recipients expect transactional mail; unexpected commercial content erodes trust

Infrastructure separation:
```yaml
# SendGrid subuser configuration
transactional:
  subuser: myapp-transactional
  ip_pool: transactional-pool
  from: noreply@yourdomain.com

marketing:
  subuser: myapp-marketing
  ip_pool: marketing-pool
  from: hello@mail.yourdomain.com
```

## Gotchas
- A transactional email with a promotional sidebar or upsell block may be classified as commercial by regulators
- CAN-SPAM uses "primary purpose" to determine classification; if > 50% of content is promotional, it is commercial
- Keep separate sending domains or at minimum subdomains for each stream

## Related
- `can-spam-compliance.md`
- `dedicated-ip-vs-shared.md`
- `email-service-provider-comparison.md`
