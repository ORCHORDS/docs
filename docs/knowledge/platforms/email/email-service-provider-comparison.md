# email-service-provider-comparison

**Issue:** Comparing major ESPs for transactional and marketing email use cases
**Date:** 2026-08-11
**Status:** documented

## Pattern / Solution

| Provider | Best for | Pricing model | Deliverability notes |
|----------|----------|--------------|---------------------|
| **Postmark** | Transactional | Per message (~$1.50/1k) | Highest deliverability; strict TOS; marketing not allowed |
| **SendGrid** | Both | Tiered by volume | Large shared pool; dedicated IPs available; strong API |
| **Resend** | Developer transactional | Per message ($0.80/1k) | Modern API; React Email native support; newer reputation |
| **Mailgun** | Transactional + API | Pay-as-you-go | Flexible routing; good inbound; EU data residency option |
| **AWS SES** | High-volume / custom infra | Per message ($0.10/1k) | Cheapest at scale; minimal hand-holding; sandbox by default |
| **Brevo (Sendinblue)** | Marketing + transactional | Tiered by sends | EU-based; GDPR-friendly; built-in CRM |
| **Klaviyo** | E-commerce marketing | Tiered by contacts | Deep Shopify integration; segmentation-first |

Key decision factors:
- **Developer experience**: Resend and Postmark have the best APIs; SES has the most complex setup
- **Volume**: SES is cheapest above 1M/month; Postmark/Resend are cost-effective below 100k
- **Deliverability sensitivity**: Postmark for critical transactional; shared pools risky for large marketing blasts
- **Inbound processing**: Mailgun and Postmark have strong inbound email APIs

## Gotchas
- SendGrid's shared IP pool reputation varies; new accounts may start on lower-reputation pools
- AWS SES requires a sandbox exit request before you can send to unverified addresses
- Mixing providers: use Postmark for transactional and Mailgun/SES for marketing is a common pattern

## Related
- `sendgrid-setup.md`
- `postmark-setup.md`
- `resend-setup.md`
- `aws-ses-setup.md`
