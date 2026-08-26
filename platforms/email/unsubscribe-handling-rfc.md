# unsubscribe-handling-rfc

**Issue:** Implementing compliant unsubscribe handling per RFC 2369 and RFC 8058
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Unsubscribe links buried in email footers lead to high complaint rates because users hit "report spam" instead.

## Pattern / Solution
**RFC 2369** — `List-Unsubscribe` header with mailto and/or URL:
```
List-Unsubscribe: <mailto:unsub-abc123@mail.yourdomain.com>, <https://yourdomain.com/unsubscribe?token=abc123>
```

**RFC 8058** — `List-Unsubscribe-Post` enables one-click unsubscribe (required by Google/Yahoo for bulk senders):
```
List-Unsubscribe: <https://yourdomain.com/unsubscribe?token=abc123>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
```

Your endpoint must:
- Accept a `POST` request (not GET) with body `List-Unsubscribe=One-Click`
- Process the unsubscribe within 2 seconds (return 200 before processing async)
- Complete the unsubscribe within 10 business days per CAN-SPAM (immediately is best practice)

```javascript
app.post('/unsubscribe', async (req, res) => {
  const { token } = req.query;
  res.sendStatus(200); // respond immediately
  const subscriber = await db.tokens.find(token);
  if (subscriber) {
    await db.subscriptions.update(
      { email: subscriber.email },
      { status: 'unsubscribed', unsubscribed_at: new Date() }
    );
  }
});
```

## Gotchas
- Gmail and Apple Mail now surface a one-click "Unsubscribe" button in the UI when RFC 8058 is present; missing it means users hit "Report Spam" instead
- The token in the URL must be opaque and single-use to prevent CSRF abuse
- Unsubscribes must propagate to all lists, not just the list used in the current campaign

## Related
- `list-unsubscribe-header.md`
- `complaint-rate-monitoring.md`
- `can-spam-compliance.md`
