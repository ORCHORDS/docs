# list-unsubscribe-header

**Issue:** Adding List-Unsubscribe and List-Unsubscribe-Post headers to outbound marketing email
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Email clients show a generic unsubscribe warning or no unsubscribe option, leading to higher spam complaints.

## Pattern / Solution
Include both headers on every marketing/bulk email:

```
List-Unsubscribe: <https://mail.yourdomain.com/unsub?uid=USER_ID&t=TOKEN>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
```

Node.js with Nodemailer:
```javascript
const message = {
  from: 'hello@yourdomain.com',
  to: recipient.email,
  subject: 'Your weekly update',
  headers: {
    'List-Unsubscribe': `<https://mail.yourdomain.com/unsub?uid=${recipient.id}&t=${recipient.unsubToken}>`,
    'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
    'List-ID': '<newsletter.yourdomain.com>',
  },
  html: emailBody,
};
```

Generate a per-recipient HMAC token:
```javascript
const crypto = require('crypto');
function unsubToken(email, secret) {
  return crypto.createHmac('sha256', secret).update(email).digest('hex');
}
```

## Gotchas
- Do NOT require the user to log in to unsubscribe; the one-click flow is a bot-initiated POST with no session
- The URL in `List-Unsubscribe` must remain valid for the lifetime of the email in the recipient's inbox (potentially years)
- Some ESPs add these headers automatically; check before adding manually to avoid duplicates

## Related
- `unsubscribe-handling-rfc.md`
- `can-spam-compliance.md`
