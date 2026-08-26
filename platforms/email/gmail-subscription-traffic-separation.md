# Gmail subscription and transactional traffic separation

**Date:** 2026-08-26
**Status:** documented
**Source:** https://support.google.com/mail/answer/15263077

## Context

Google's Gmail subscription guidance recommends sending subscription messages and non-subscription messages from different email addresses.

## Pattern

Separate traffic classes such as:

- marketing/newsletters/subscription notifications;
- password resets, receipts, OTPs, and other transactional mail.

Use distinct sender identities so reputation, suppression, and unsubscribe handling for promotional traffic do not accidentally interfere with account-critical mail.

## Operational controls

- Route each traffic class through an explicit sending configuration.
- Apply unsubscribe logic only where appropriate.
- Keep authentication valid for every sender identity.
- Monitor reputation and failures by traffic class.
- Prevent campaign tooling from using a transactional sender by default.

## Verification

Send representative messages from both classes and verify:

1. distinct `From:` identities are used;
2. promotional suppression does not block a required transactional message;
3. transactional messages are not incorrectly given marketing-list semantics;
4. authentication and DNS alignment remain correct for both paths.

## Boundary

Message classification can also be affected by applicable law and recipient expectations; this entry documents Gmail operational guidance rather than legal advice.
