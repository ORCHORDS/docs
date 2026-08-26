# ses-bounce-complaint-webhooks

**Issue:** Handling SES bounce and complaint notifications via SNS webhooks
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
SES accounts get suspended when bounce rate exceeds 5% or complaint rate exceeds 0.1%. Automated handling is essential.

## Pattern / Solution
1. In SES > Configuration Sets, create a configuration set with an SNS destination for `Bounce` and `Complaint` event types.
2. Create an SNS topic and subscribe an HTTPS endpoint (Lambda URL or API Gateway).
3. Parse SNS notification:
```js
const body = JSON.parse(req.body);
if (body.Type === 'SubscriptionConfirmation') {
  await fetch(body.SubscribeURL);
  return;
}
const msg = JSON.parse(body.Message);
if (msg.notificationType === 'Bounce') {
  suppressEmails(msg.bounce.bouncedRecipients);
}
if (msg.notificationType === 'Complaint') {
  suppressEmails(msg.complaint.complainedRecipients);
}
```
4. Add suppressed addresses to your suppression list immediately.
5. For hard bounces, never retry. For complaints, unsubscribe permanently.

## Gotchas
- SNS sends subscription confirmation as first message; must confirm before receiving events.
- SES account-level suppression list is separate from configuration-set-level notifications.
- Soft bounce retry logic should use exponential backoff (max 3 attempts over 72 hours).
- SES also has an account-level suppression list at `SES > Suppression List`; add hard bounces there too.

## Related
- bounce-handling-hard-soft, complaint-rate-monitoring, suppression-list-management, aws-ses-setup
