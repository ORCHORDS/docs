# stripe-apple-pay-setup

**Issue:** Enabling Apple Pay in Stripe payment flows
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Apple Pay lets users pay with Face ID/Touch ID on Safari and iOS. It increases conversion on mobile by eliminating card entry.

## Pattern / Solution
Apple Pay appears automatically in Payment Element when using HTTPS and Safari/iOS. Manual domain verification is required:

1. In Stripe Dashboard > Settings > Payment methods > Apple Pay: add your domain
2. Serve the verification file at `/.well-known/apple-developer-merchantid-domain-association`

```typescript
// In Workers: serve the file
if (url.pathname === '/.well-known/apple-developer-merchantid-domain-association') {
  const file = await env.KV.get('apple-pay-verification');
  return new Response(file, { headers: { 'Content-Type': 'text/plain' } });
}
```

Download the file from Stripe and store it in KV.

## Gotchas
- Apple Pay only works on HTTPS — localhost requires a tunnel or test with ngrok
- Each domain (including subdomains) requires separate verification
- Apple Pay is not shown in Chrome or Firefox — it is Safari/WebKit-only
- Payment Element handles the Apple Pay button styling automatically

## Related
- `stripe-payment-elements.md`
- `stripe-google-pay-setup.md`
