# email-spam-triggers

**Issue:** Avoiding content patterns that trigger spam filters
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Email goes to spam despite good authentication setup because content patterns match spam heuristics.

## Pattern / Solution
High-risk content patterns to avoid:
1. **Words:** FREE, URGENT, GUARANTEED, 100% free, CLICK HERE, Act Now, Limited time.
2. **Formatting:** ALL CAPS, excessive exclamation marks (!!!), red text, large fonts.
3. **Links:** URL shorteners, mismatched link text/href, links to suspicious TLDs.
4. **Structure:** No plain text part, image-only emails, single large image with no text.
5. **HTML:** Invisible/tiny text, `display:none` used excessively, comment stuffing.
6. **Ratio:** Over 60% images to text ratio is a spam signal.

## Gotchas
- Spam filters use ensemble scoring; one trigger rarely fails delivery, but combinations do.
- Legitimate urgency language in transactional emails (e.g., "reset expires in 24 hours") is generally safe.
- URL shorteners are heavily penalized; always link to your own domain.
- Test with SpamAssassin locally or use Mail-tester.com before major sends.

## Related
- spam-assassin-scoring, email-content-guidelines, email-deliverability-fundamentals, email-authentication-check-tools
