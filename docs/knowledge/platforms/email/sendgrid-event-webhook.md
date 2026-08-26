# sendgrid-event-webhook

**Issue:** Configuring SendGrid Event Webhook for real-time delivery tracking
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Applications need real-time delivery status (delivered, bounced, opened, clicked, complained) to update records and suppress addresses.

## Pattern / Solution
1. Go to SendGrid > Settings > Mail Settings > Event Webhook.
2. Enter your HTTPS endpoint URL, select event types (delivered, bounce, open, click, spam report, unsubscribe).
3. Enable Signed Event Webhook and store the verification key.
4. Verify signature in your handler:
```js
import { EventWebhook } from '@sendgrid/eventwebhook';
const ew = new EventWebhook();
const key = ew.convertPublicKeyToECDSA(process.env.SENDGRID_WEBHOOK_KEY);
const valid = ew.verifySignature(key, payload, signature, timestamp);
```
5. Process events array (batched): update DB status, add bounces/complaints to suppression list.

## Gotchas
- Events are batched and POSTed as JSON arrays; process atomically.
- SendGrid retries failed webhook deliveries for 72 hours with exponential backoff.
- Respond with 2xx within 10 seconds or SendGrid marks delivery as failed.
- `sg_message_id` links events back to your send records.
- Open events are unreliable due to Apple MPP and image blocking.

## Related
- email-open-tracking, email-click-tracking, bounce-handling-hard-soft, sendgrid-setup
