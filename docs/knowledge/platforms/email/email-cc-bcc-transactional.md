# email-cc-bcc-transactional

**Issue:** Using CC and BCC correctly in transactional email flows
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Transactional flows sometimes need to notify multiple parties (e.g., CC manager on invoice, BCC compliance on contracts).

## Pattern / Solution
1. CC: Use for recipients who should be visible to the To recipient (e.g., account manager CC on invoice).
2. BCC: Use for silent copies — compliance, audit logs, CRM integration.
3. Most ESPs support CC/BCC in API:
```js
await sendgrid.send({
  to: 'customer@example.com',
  cc: 'manager@acme.com',
  bcc: 'audit@acme.com',
  // ...
});
```
4. For BCC to CRM: use BCC to a Salesforce/HubSpot email-to-CRM address.
5. Avoid CC on marketing emails; GDPR requires each recipient to have consented independently.

## Gotchas
- BCC recipients receive all Reply-All replies in some clients if not handled carefully.
- CC/BCC count against ESP rate limits and billing; each recipient counts as one email.
- Some deliverability tools flag emails with large CC lists as spam risk.
- GDPR: BCC-ing a third party on an email without recipient knowledge may require legal basis.

## Related
- email-from-name-strategy, transactional-vs-marketing-email, gdpr-email-consent
