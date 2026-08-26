# email-reply-to-patterns

**Issue:** Configuring Reply-To header for different email flow scenarios
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The Reply-To header determines where replies go, which may differ from the sending address in automated email workflows.

## Pattern / Solution
1. **Support tickets:** Send from `noreply@acme.com`, Reply-To `support+ticket #<number>@acme.com` to route replies to the ticket.
2. **Sales outreach:** Reply-To sender's personal address even when sending via ESP.
3. **Inbound reply processing:** Reply-To `reply+{{token}}@inbound.acme.com` to correlate replies.
4. **No reply needed:** Reply-To can be omitted; MUAs default to From address.
5. Set Reply-To in most ESPs:
```js
await resend.emails.send({
  from: 'noreply@acme.com',
  replyTo: 'support@acme.com',
  // ...
});
```

## Gotchas
- Reply-To does not affect deliverability; only From domain is authenticated.
- Some anti-spam filters flag when Reply-To domain differs significantly from From domain.
- Email threads in Gmail group by subject; Reply-To doesn't control threading.

## Related
- email-from-name-strategy, inbound-email-processing, email-to-ticket-pattern, postmark-inbound-email
