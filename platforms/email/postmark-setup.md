# postmark-setup

**Issue:** Setting up Postmark for high-deliverability transactional email
**Date:** 2026-08-11
**Status:** documented

## Pattern / Solution
1. Create account → Add Sender Signature or Domain
2. For domain sending, add DNS records:
   ```
   # DKIM
   20240101._domainkey.yourdomain.com TXT "v=DKIM1; k=rsa; p=<key>"
   # Return-Path (for bounce handling)
   pm-bounces.yourdomain.com CNAME pm.mtasv.net
   ```
3. Verify → create a Server → get Server API Token

Send with Node.js:
```javascript
const postmark = require('postmark');
const client = new postmark.ServerClient(process.env.POSTMARK_SERVER_TOKEN);

await client.sendEmail({
  From: 'noreply@yourdomain.com',
  To: 'user@example.com',
  Subject: 'Reset your password',
  HtmlBody: '<p>Click <a >here</a> to reset.</p>',
  TextBody: 'Reset link: {{link}}',
  MessageStream: 'outbound',  // or a broadcast stream for marketing
  Tag: 'password-reset',
  TrackOpens: true,
  TrackLinks: 'HtmlAndText',
  Metadata: { user_id: '12345' },
});
```

Message streams: Postmark separates transactional (`outbound`) and marketing (`broadcast`) into separate streams with separate reputation pools. Create a broadcast stream for newsletters.

Webhooks: Settings → Servers → [server] → Webhooks → add URL for: Bounce, SpamComplaint, Open, Click.

## Gotchas
- Postmark enforces strict TOS: no cold outreach, no purchased lists, no newsletters on the transactional stream
- Using templates: Postmark's template API requires the template to be created in the UI first, then referenced by alias in the API call
- The `pm-bounces.` CNAME is required for proper bounce processing; without it, bounces go to Postmark's generic return path

## Related
- `postmark-inbound-email.md`
- `email-service-provider-comparison.md`
- `bounce-handling-hard-soft.md`
