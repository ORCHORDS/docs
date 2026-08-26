# email-click-tracking

**Issue:** Tracking link clicks in emails via redirect URLs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Click tracking is the most reliable engagement signal in email, but implementation requires careful URL rewriting.

## Pattern / Solution
1. Replace original URLs with redirect URLs:
```
Original: https://app.yourdomain.com/dashboard
Tracked:  https://track.yourdomain.com/click?id={{messageId}}&url=aHR0cHM...&sig=abc
```
2. Redirect endpoint: validate signature, log click event, redirect to destination.
3. Use click-tracking domain with valid SSL and same root domain as sending domain for deliverability.
4. Include HMAC signature on redirect URLs to prevent URL manipulation.
5. Map clicks back to message IDs in your analytics pipeline.

## Gotchas
- Branded click-tracking domains improve deliverability vs. ESP-shared domains.
- Security scanners (corporate proxies, anti-phishing bots) follow links and register false clicks.
- Apple MPP does NOT pre-fetch clicked links, so click data is more reliable than opens.
- Long redirect chains add latency; keep under 2 hops.
- URL parameters must survive redirect; encode destination URL as base64, not raw query param.

## Related
- email-open-tracking, tracking-pixel-privacy, email-analytics-metrics, email-a-b-testing
