# tracking-pixel-privacy

**Issue:** Privacy implications and compliance requirements for email tracking pixels
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
GDPR, ePrivacy, and platform-level privacy protections (Apple MPP) have changed what email tracking can and cannot do.

## Pattern / Solution
1. Disclose tracking in privacy policy: "We use tracking pixels to measure email open rates."
2. For GDPR: tracking pixels in marketing emails require consent; transactional emails may use legitimate interest if minimal.
3. Provide opt-out of tracking via email preference center.
4. Design analytics to handle inflated open rates: use click rate as primary engagement KPI.
5. Consider server-side tracking alternatives: measure link clicks without pixel tracking.
6. Strip tracking from plain-text versions entirely.

## Gotchas
- Apple MPP affects ~40-60% of email opens depending on audience; do not use open rate for send-time optimization.
- Canada's CASL does not specifically regulate tracking pixels, but consent for marketing email is required.
- CAN-SPAM does not restrict tracking pixels.
- Some ESPs allow disabling open tracking per-send for privacy-sensitive content.

## Related
- email-open-tracking, gdpr-email-consent, email-preference-center, email-analytics-metrics
