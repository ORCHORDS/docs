# aws-ses-setup

**Issue:** Configuring Amazon SES for high-volume email at low cost
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
High-volume senders want infrastructure-level email at $0.10/1000 emails without per-seat pricing.

## Pattern / Solution
1. Verify domain in SES console: add DKIM records (3 CNAME records), SPF via custom MAIL FROM domain.
2. Request production access (exits sandbox) via SES > Account Dashboard > Request Production Access.
3. Send via SDK:
```js
import { SESv2Client, SendEmailCommand } from '@aws-sdk/client-sesv2';
const client = new SESv2Client({ region: 'us-east-1' });
await client.send(new SendEmailCommand({
  FromEmailAddress: 'no-reply@yourdomain.com',
  Destination: { ToAddresses: ['user@example.com'] },
  Content: { Simple: { Subject: { Data: 'Hello' }, Body: { Html: { Data: '<p>Hi</p>' } } } }
}));
```
4. Configure SNS notifications for bounces and complaints, process via Lambda or SQS.
5. Set up configuration sets to route event data to Kinesis, CloudWatch, or SNS.

## Gotchas
- Sandbox mode only allows sending to verified emails. Production access requires justification.
- Default sending limits: 200/day sandbox, 50,000/day production (raiseable).
- MAIL FROM domain must be a subdomain (e.g., `mail.yourdomain.com`) for proper SPF alignment.
- SES does not manage suppression lists automatically; integrate bounce/complaint webhooks manually.

## Related
- ses-bounce-complaint-webhooks, ip-warming-strategy, spf-record-setup, dkim-record-setup
