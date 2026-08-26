# Gmail one-click unsubscribe requirements

**Date:** 2026-08-26
**Status:** documented
**Sources:**
- https://support.google.com/mail/answer/81126?hl=en
- https://support.google.com/mail/answer/14229414?hl=en
- https://support.google.com/mail/answer/15263077?hl=en

## Context

Gmail applies additional requirements to senders that send more than 5,000 messages per day to Gmail accounts. Marketing and subscription messages from those bulk senders must support one-click unsubscribe.

## Required mechanism

Google documents RFC 8058-style one-click unsubscribe using both headers:

```text
List-Unsubscribe-Post: List-Unsubscribe=One-Click
List-Unsubscribe: <https://example.com/unsubscribe/token>
```

The HTTPS endpoint must process the unsubscribe without requiring another confirmation page or user action.

## Operational requirements

- Apply one-click unsubscribe to marketing, promotional, and subscription messages that fall under Gmail's bulk-sender requirements.
- Keep a clearly visible unsubscribe option in the message body as required by Google's sender guidelines.
- Honor unsubscribe requests within 48 hours for subscription messages.
- Do not assume a `mailto:` unsubscribe or a preference-center link alone satisfies Gmail's one-click requirement.
- Keep transactional mail such as password resets and receipts separate from subscription traffic where practical.

## Verification

1. Inspect the raw delivered message and confirm both one-click headers are present where required.
2. POST to the unsubscribe URL and verify the recipient is suppressed without an additional interactive step.
3. Confirm suppression propagates to every relevant sending path.
4. Monitor Gmail Postmaster Tools and keep spam rates below Google's documented 0.30% threshold.

## Gotchas

- A normal unsubscribe link in HTML does not by itself satisfy one-click unsubscribe.
- Google states that enforcement of non-compliant traffic has been ramping up since November 2025.
- Transactional messages are excluded from the one-click requirement, but classification must reflect the actual message purpose.

## Related

- `gmail-sender-authentication-requirements.md`
