# stripe-pix-brazil

**Issue:** Accepting Pix instant payments for Brazilian customers via Stripe
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Pix is Brazil's instant payment network operated by the Central Bank. It settles in seconds, 24/7, and is widely adopted across Brazilian consumers and businesses.

## Pattern / Solution
```typescript
const paymentIntent = await stripe.paymentIntents.create({
  amount: 5000,
  currency: 'brl',
  payment_method_types: ['pix'],
  payment_method_options: {
    pix: { expires_after_seconds: 3600 }, // 1 hour
  },
});

// After creation, retrieve QR code
const pixDetails = paymentIntent.next_action?.pix_display_qr_code;
const qrCodeImageUrl = pixDetails?.image_url_png;
const qrCodeData = pixDetails?.data; // raw string for QR generation
```

Display the QR code to the customer. Poll `paymentIntent.status` or listen to `payment_intent.succeeded` webhook.

## Gotchas
- Pix QR codes expire — set a reasonable `expires_after_seconds` and show a countdown timer
- Pix is BRL only
- Unlike Boleto, Pix confirmation is near-instant (seconds)
- Refunds via Pix are supported but go through Stripe's standard refund flow
- Pix keys (CPF, CNPJ, email, phone) are not used in the Stripe API — only QR code flow

## Related
- `stripe-boleto-brazil.md`
