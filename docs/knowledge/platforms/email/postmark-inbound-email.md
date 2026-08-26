# postmark-inbound-email

**Issue:** Processing inbound email via Postmark's inbound webhook
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Applications receiving email (support tickets, reply processing, email-to-action) need a reliable inbound parsing pipeline.

## Pattern / Solution
1. In Postmark > Servers > Inbound, set the inbound webhook URL.
2. Add Postmark's MX record (`inbound.postmarkapp.com`) for your inbound domain or subdomain (e.g., `reply.yourdomain.com`).
3. Postmark parses the email and POSTs JSON to your endpoint:
```js
app.post('/inbound', (req, res) => {
  const { From, Subject, TextBody, HtmlBody, Attachments, Headers } = req.body;
  // process email
  res.sendStatus(200);
});
```
4. Use `ReplyTo` header or `+tag` addressing to correlate replies to original records.
5. Validate sender domain or address before processing to prevent spoofed inbound spam.

## Gotchas
- Postmark's inbound address is `yourtoken@inbound.postmarkapp.com` by default; custom domain requires MX setup.
- Attachments are base64-encoded in the JSON payload; decode before storing.
- Maximum inbound message size is 10 MB including attachments.
- Respond 200 immediately; process async to avoid timeout.

## Related
- email-to-ticket-pattern, email-parsing-patterns, inbound-email-processing, email-forwarding-setup
