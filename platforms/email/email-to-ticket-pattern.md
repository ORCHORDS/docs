# email-to-ticket-pattern

**Issue:** Converting inbound email replies into support tickets automatically
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Support teams need customer email replies to automatically create or update tickets without manual processing.

## Pattern / Solution
1. Assign each ticket a unique reply-to address: `support+ticket-{id}@inbound.acme.com`.
2. Set this as `Reply-To` in outbound support emails.
3. Inbound webhook receives reply:
```js
const match = message.to.match(/ticket-(\d+)/);
if (match) {
  await updateTicket(match[1], message);
} else {
  await createTicket(message);
}
```
4. Extract body excluding quoted reply using `email-reply-parser` library.
5. Attach any inbound attachments to the ticket.
6. Send auto-reply confirming ticket creation/update.

## Gotchas
- `email-reply-parser` must handle various quoting styles (Gmail, Outlook, Apple Mail).
- Some users reply to the noreply address; have a catch-all that creates new tickets.
- Forwarded emails look like replies; detect via "Forwarded message" header/content.
- Loop prevention: never auto-reply to `Auto-Submitted: auto-replied` header.

## Related
- inbound-email-processing, email-parsing-patterns, email-reply-to-patterns, postmark-inbound-email
