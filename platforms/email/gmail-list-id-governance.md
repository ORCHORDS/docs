# Gmail subscription List-ID governance

**Date:** 2026-08-26
**Status:** documented
**Source:** https://support.google.com/mail/answer/15263077

## Context

Google's current subscription-message guidance recommends identifying each subscription list with a human-readable `List-ID:` header or using a unique `From:` address for separate subscriptions.

## Pattern

- Give every independent mailing list a stable, human-understandable identity.
- Keep the identifier tied to one subscription purpose instead of reusing it across unrelated campaigns.
- Make unsubscribe processing list-scoped when that is the intended user choice.
- Keep sender configuration and list metadata version-controlled or otherwise change-controlled.

## Anti-patterns

- One opaque list identity for unrelated products or topics.
- Changing `List-ID` on every campaign.
- Using list metadata to override a user's prior unsubscribe state.
- Putting personal data, tokens, customer IDs, or internal infrastructure identifiers into public-facing header values.

## Verification

Inspect delivered message source and confirm the intended list identity is present and stable. Exercise one-click unsubscribe and prove it removes the recipient from the intended subscription without unexpectedly suppressing unrelated transactional mail.
