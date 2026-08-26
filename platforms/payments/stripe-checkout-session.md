# stripe-checkout-session

**Issue:** Creating and redirecting to a Stripe-hosted Checkout session
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
You want a hosted payment page without building your own UI. Stripe Checkout handles card input, 3DS, and receipt emails automatically.

## Pattern / Solution
```typescript
const session = await stripe.checkout.sessions.create({
  mode: 'payment',
  line_items: [{ price: 'price_xxx', quantity: 1 }],
  success_url: 'https://example.com/success?session_id={CHECKOUT_SESSION_ID}',
  cancel_url: 'https://example.com/cancel',
  customer_email: user.email,
  metadata: { userId: user.id },
});
return Response.redirect(session.url, 303);
```

Verify completion via `checkout.session.completed` webhook before fulfilling the order.

## Gotchas
- `{CHECKOUT_SESSION_ID}` is a Stripe template variable — do not replace it yourself
- Always verify the webhook event rather than trusting the success_url redirect
- Session URLs expire after 24 hours
- Use `customer` param instead of `customer_email` for returning customers to avoid duplicate customer records

## Related
- `stripe-webhook-setup.md`
- `stripe-payment-intents.md`
