# sendgrid-setup

**Issue:** Setting up SendGrid for transactional or marketing email sending
**Date:** 2026-08-11
**Status:** documented

## Pattern / Solution
1. Create account → Settings → Sender Authentication → Domain Authentication
2. Add CNAME records provided by SendGrid to your DNS:
   ```
   em1234.yourdomain.com CNAME u1234567.wl234.sendgrid.net
   s1._domainkey.yourdomain.com CNAME s1.domainkey.u1234567.wl234.sendgrid.net
   s2._domainkey.yourdomain.com CNAME s2.domainkey.u1234567.wl234.sendgrid.net
   ```
3. Verify in SendGrid UI

API key scoping:
```json
{
  "name": "app-transactional",
  "scopes": ["mail.send", "stats.read", "suppression.read", "suppression.write"]
}
```

Send with Node.js SDK:
```javascript
const sgMail = require('@sendgrid/mail');
sgMail.setApiKey(process.env.SENDGRID_API_KEY);
await sgMail.send({
  to: 'user@example.com',
  from: { email: 'noreply@yourdomain.com', name: 'YourApp' },
  subject: 'Your order shipped',
  html: '<p>It is on its way!</p>',
  customArgs: { order_id: '12345' },  // passed back in webhooks
});
```

Set up event webhook: Settings → Mail Settings → Event Webhook → enter your endpoint URL, select: bounce, spam report, unsubscribe.

## Gotchas
- The API key is shown only once at creation; store it in a secret manager immediately
- Subusers are the way to separate transactional and marketing streams in SendGrid; use them
- Click tracking rewrites links through `sendgrid.net` by default; this can break branded link domains — set up link branding
- Rate limit: 10,000 requests/sec on the v3 API (rarely a practical concern)

## Related
- `sendgrid-event-webhook.md`
- `email-service-provider-comparison.md`
- `dkim-record-setup.md`
