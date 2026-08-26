# email-open-tracking

**Issue:** Implementing and interpreting email open tracking pixels
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Marketing teams need to measure email engagement, but open tracking has become unreliable due to privacy changes.

## Pattern / Solution
1. Insert a 1x1 transparent GIF via a tracking server URL:
```html
<img src="https://track.yourdomain.com/open?id={{messageId}}" width="1" height="1" alt="" style="display:none;" />
```
2. Tracking server logs the request, marks message as opened, returns the GIF.
3. Use open rate as a directional metric only, not absolute truth.
4. Combine with click tracking for more reliable engagement signals.
5. Segment by email client to identify bot/proxy pre-fetching patterns.

## Gotchas
- Apple Mail Privacy Protection (iOS 15+) pre-fetches tracking pixels; inflates open rates 30-50%.
- Gmail image proxy caches images; server-side logs show Google's IP, not recipient's.
- Some corporate firewalls pre-fetch all links and images, causing false opens.
- GDPR and ePrivacy Directive may require disclosure of tracking in privacy policy.

## Related
- email-click-tracking, tracking-pixel-privacy, email-analytics-metrics, sendgrid-event-webhook
