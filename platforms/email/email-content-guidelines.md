# email-content-guidelines

**Issue:** Content guidelines for maintaining deliverability and compliance across email types
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Content quality affects both spam filtering and legal compliance; guidelines need to span technical and editorial concerns.

## Pattern / Solution
Technical:
- Maintain 60/40 text-to-image ratio.
- Always include a physical mailing address (CAN-SPAM, CASL requirement).
- Include unsubscribe link in all marketing emails.
- Link to privacy policy.

Editorial:
- Do not make false urgency claims.
- Do not use misleading subject lines.
- Proofread for spelling errors (spam signals).
- Avoid excessive punctuation and capitalization.

Segmentation:
- Do not send marketing email to transactional-only subscribers.
- Match content to subscriber's stated preferences.

## Gotchas
- Physical address requirement is US-specific (CAN-SPAM) but recommended globally.
- "This is not spam" is a spam trigger phrase.
- Including testimonials or reviews is fine; fabricated ones are an FTC violation.

## Related
- can-spam-compliance, casl-canada-compliance, email-spam-triggers, spam-assassin-scoring
