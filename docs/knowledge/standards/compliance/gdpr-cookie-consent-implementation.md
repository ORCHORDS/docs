# gdpr-cookie-consent-implementation

**Issue:** Implementing GDPR-compliant cookie consent management platforms and banners
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
ePrivacy Directive (Cookie Law) + GDPR require informed, freely given, specific, and unambiguous consent before setting non-essential cookies. Regulators actively enforce against dark patterns and pre-ticked boxes.

## Pattern / Solution
Cookie categories requiring consent:
- Analytics cookies (Google Analytics, Mixpanel) — require consent
- Marketing/advertising cookies (Meta Pixel, Google Ads) — require consent
- Personalization cookies — require consent
- Strictly necessary cookies (session, CSRF token, load balancer) — no consent required

Consent banner requirements (EDPB guidelines):
- Equal prominence for Accept and Reject/Decline buttons (same size, color, position)
- No pre-ticked checkboxes
- Granular category controls available
- Withdrawal as easy as giving consent (settings link in footer)
- Re-show banner if consent expires (typically 12 months) or user withdraws

Technical implementation:
```javascript
// Consent-conditional loading
if (getCookieConsent('analytics')) {
  loadGoogleAnalytics();
}

// Prefer tag manager with consent mode
gtag('consent', 'default', {
  'analytics_storage': 'denied',
  'ad_storage': 'denied'
});
// Update after consent
gtag('consent', 'update', {
  'analytics_storage': consent.analytics ? 'granted' : 'denied'
});
```

CMP platforms: OneTrust, Cookiebot, Usercentrics, CookieYes — all support IAB TCF 2.2 for ad tech.

Store consent records: timestamp, consent string, user ID (if authenticated), banner version, granular choices. Retain 3 years minimum.

## Gotchas
- "Soft nudge" banners (grey reject button, green accept button) are fined by DPAs
- Legitimate interest for analytics is rejected by most European DPAs — use consent
- Cookie audit required periodically — new third-party scripts add unconsented cookies
- UK ICO and French CNIL have different nuances — verify per jurisdiction

## Related
- `gdpr-consent-management.md`
- `gdpr-privacy-notice-template.md`
- `privacy-by-design-checklist.md`
