# email-preference-center

**Issue:** Building an email preference center for subscriber self-management
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
One-click unsubscribe loses subscribers who just want fewer emails; a preference center retains them with granular control.

## Pattern / Solution
Preference options:
- Notification types (security alerts, product updates, weekly digest, marketing).
- Frequency (daily, weekly, monthly digest).
- Topic preferences (feature announcements, company news, usage tips).
- One-click global unsubscribe at bottom.

Implementation:
```js
app.get('/preferences', authenticate, async (req, res) => {
  const prefs = await getUserEmailPreferences(req.user.id);
  res.render('preferences', { prefs });
});

app.post('/preferences', authenticate, async (req, res) => {
  await updateEmailPreferences(req.user.id, req.body);
  res.redirect('/preferences?saved=true');
});
```

Access: link in every email footer; no login required (use signed token).

## Gotchas
- Preference center must be accessible without login (many users are signed out when reading email).
- Use signed, expiring tokens in preference center URLs to authenticate without password.
- Security alert emails must not be disableable; they are mandatory transactional.
- GDPR: preferences are not consent; re-record consent separately from preferences.

## Related
- list-unsubscribe-header, unsubscribe-handling-rfc, email-frequency-capping, email-fatigue-prevention
