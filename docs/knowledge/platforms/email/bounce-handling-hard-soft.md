# bounce-handling-hard-soft

**Issue:** Correctly classifying and acting on email bounce notifications
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
High bounce rates damage sender reputation; continuing to send to bouncing addresses compounds the problem.

## Pattern / Solution
**Hard bounce** (permanent failure — suppress immediately):
- SMTP 5xx response: `550 5.1.1 User unknown`
- Address does not exist, domain does not exist, account closed
- Action: add to suppression list immediately; never retry

**Soft bounce** (temporary failure — retry with backoff):
- SMTP 4xx response: `452 4.2.2 Mailbox full`
- Causes: mailbox full, server temporarily unavailable, rate limiting
- Action: retry exponentially; hard-suppress after 3–5 consecutive soft bounces

Webhook handling (SendGrid example):
```javascript
app.post('/webhooks/sendgrid', (req, res) => {
  for (const event of req.body) {
    if (event.event === 'bounce') {
      // type: 'bounce' = hard, 'blocked' = soft/reputation
      if (event.type === 'bounce') {
        db.suppressions.insert({ email: event.email, reason: 'hard_bounce' });
      }
    }
    if (event.event === 'dropped') {
      // Already on suppression list at provider level
      db.suppressions.upsert({ email: event.email });
    }
  }
  res.sendStatus(200);
});
```

SMTP bounce code reference:
- `550` — mailbox unavailable
- `551` — user not local
- `552` — storage exceeded (sometimes hard)
- `553` — mailbox name not allowed
- `421` — service temporarily unavailable (soft)

## Gotchas
- ISPs sometimes send a 2xx (accepted) then later send a bounce-back NDR message — this is an asynchronous bounce; parse inbound mail to your bounce address
- "Blocked" events at provider level often indicate IP or domain reputation issues, not address invalidity — investigate before suppressing
- Keep a timestamped bounce log; some addresses recover (e.g., former employee account reopened)

## Related
- `suppression-list-management.md`
- `email-queue-architecture.md`
- `ses-bounce-complaint-webhooks.md`
