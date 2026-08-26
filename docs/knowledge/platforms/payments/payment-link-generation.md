# payment-link-generation

**Issue:** Creating shareable payment links for one-time or recurring charges without a full checkout integration
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Payment links allow collecting payments via email, SMS, or social media without embedding Stripe.js. Stripe's hosted payment links are quick to set up but have limited customization.

## Pattern / Solution
Create via Stripe Dashboard or API: POST /v1/payment_links with line_items referencing price IDs. For dynamic amounts, use a checkout session with customer_creation=always and a success URL. For custom checkout links with metadata, create sessions server-side and return the URL.

## Gotchas
Stripe payment links do not expire by default — set expires_at if needed. Reusing the same link for multiple customers means you cannot pre-fill customer data. For B2B invoicing, use Stripe hosted invoice links instead.

## Related
stripe-checkout-session, invoice-generation-pdf, one-click-upsell
