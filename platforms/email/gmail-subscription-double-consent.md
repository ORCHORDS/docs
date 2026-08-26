# Gmail subscription double-consent guidance

**Date:** 2026-08-26
**Status:** documented
**Source:** https://support.google.com/mail/answer/15263077

## Context

Google's current subscription-message guidance tells senders to confirm a recipient's email address after it is entered on a website or app before sending subscription messages. Google describes this as double consent.

## Pattern

1. Collect the address with an explicit subscription action.
2. Send a confirmation message to that address.
3. Do not activate the marketing/subscription list membership until confirmation succeeds.
4. Record only the evidence needed to prove the subscription state and respect retention requirements.
5. Make resubscription and unsubscribe transitions explicit rather than silently restoring old consent.

## Why it matters

Address confirmation reduces accidental subscriptions, typo-driven mail, and abuse where one person submits another person's address.

## Verification

- An unconfirmed address receives no subscription campaign traffic.
- Confirmation activates only the intended list.
- Expired or invalid confirmation links fail closed.
- Unsubscribe remains effective after later unrelated account activity.

## Boundary

This page documents Gmail sender guidance, not a universal legal definition of consent. Applicable privacy/marketing law must be assessed separately for the recipient and sender jurisdictions.
