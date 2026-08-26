# Gmail Promotions tab annotation governance

**Issue:** Gmail can render promotional email annotations beyond the normal subject and body. Incorrect, stale, or misleading structured data can create a presentation that no longer matches the actual offer.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented — provider-specific enhancement; rendering is not guaranteed

## Decision

Treat Promotions annotations as optional metadata generated from the same authoritative campaign record as the email body. The message must remain complete and truthful when Gmail ignores every annotation.

## Controls

- Generate JSON-LD or Microdata from one validated campaign model, never manually duplicated offer facts.
- Validate offer code, description, start/end dates, sender branding, image URL, and landing URL before send.
- Reject expired offers and prohibit annotations that overstate the body.
- Use stable HTTPS image and landing URLs with appropriate public access.
- Keep unsubscribe, consent, suppression, and frequency controls independent of annotations.
- Avoid user-specific or sensitive data in markup.
- Apply Gmail’s image quality, format, dimension, and URL constraints.
- Version templates and retain the rendered source associated with an approved campaign.

## Verification

Run Gmail’s annotation preview validation on representative messages. Send seeded tests to supported and unsupported clients, with images blocked, and after the offer expires. Confirm the ordinary MIME content conveys all required terms and that markup changes do not break authentication alignment or unsubscribe behavior.

## Gotchas

Gmail decides whether and how to show annotations. Preview success is not a delivery or placement guarantee. Cached images and delayed delivery can outlive a promotion, so the landing page must enforce current terms.

## Sources

- [Google: Annotate emails in the Promotions tab](https://developers.google.com/workspace/gmail/promotab/overview)
- [Google Promotions annotation preview](https://developers.google.com/workspace/gmail/promotab/preview)
- [Google Promotions annotations best practices](https://developers.google.com/workspace/gmail/promotab/best-practices)
