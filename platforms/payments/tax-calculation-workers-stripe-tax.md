# tax-calculation-workers-stripe-tax

**Date:** 2026-08-22
**Author:** example.com
**Repo:** example-org/example-repo
**Status:** published

## Symptom

example project sells subscriptions globally. Different jurisdictions require
different tax rates: EU VAT (MOSS → OSS), US state sales tax, UK VAT,
Australian GST. Building a tax engine from scratch is prohibitively
complex. Stripe Tax calculates the correct rate, generates compliant
line items, and integrates with filing.

## Context

Stripe Tax is activated per-object (`automatic_tax: { enabled: true }`)
and requires:
1. At least one active tax registration in Stripe Dashboard matching
   the jurisdiction where the customer is located.
2. A customer object with a valid billing address **before** the
   calculation runs.

In a Cloudflare Worker, the customer's geographic location is available
from the `CF-IPCountry` request header (ISO 3166-1 alpha-2, set by
Cloudflare on every incoming request). example project uses this as the
initial location hint when the customer's billing address is not yet
known, then refines with the verified address collected during checkout.

## Inferring jurisdiction from CF-IPCountry

```typescript
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const countryCode = req.headers.get('CF-IPCountry') ?? 'US';
    const taxConfig = buildTaxConfig(countryCode);
    // Pass taxConfig to the checkout creation flow
    return createCheckout(req, env, taxConfig);
  },
};

interface TaxConfig {
  applyTax: boolean;
  displayHint: string;   // e.g. "VAT will be calculated at checkout"
  collectVatId: boolean; // true for EU B2B
}

function buildTaxConfig(country: string): TaxConfig {
  const euVatCountries = new Set([
    'AT','BE','BG','CY','CZ','DE','DK','EE','ES','FI',
    'FR','GR','HR','HU','IE','IT','LT','LU','LV','MT',
    'NL','PL','PT','RO','SE','SI','SK',
  ]);
  if (euVatCountries.has(country)) {
    return {
      applyTax: true,
      displayHint: 'VAT included at applicable rate',
      collectVatId: true,   // offer VAT ID for reverse charge
    };
  }
  if (country === 'GB') {
    return { applyTax: true, displayHint: 'UK VAT will apply',
             collectVatId: false };
  }
  if (country === 'AU') {
    return { applyTax: true, displayHint: 'GST included',
             collectVatId: false };
  }
  if (country === 'US') {
    return { applyTax: true, displayHint: 'Tax calculated at checkout',
             collectVatId: false };
  }
  return { applyTax: false, displayHint: '', collectVatId: false };
}
```

`CF-IPCountry` is `XX` for Tor exit nodes and some proxied requests;
default to `US` or omit automatic tax for unknown codes.

## Stripe Checkout with automatic_tax

```typescript
async function createCheckout(
  req: Request, env: Env, taxConfig: TaxConfig
): Promise<Response> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY);
  const body   = await req.json() as { customerId: string; priceId: string };

  // Ensure the customer has an address (collected during sign-up)
  // Stripe Tax silently skips tax if the address is absent
  const customer = await stripe.customers.retrieve(body.customerId);
  if (!customer || customer.deleted)
    return new Response('Customer not found', { status: 404 });

  const session = await stripe.checkout.sessions.create({
    customer: body.customerId,
    mode: 'subscription',
    line_items: [{ price: body.priceId, quantity: 1 }],
    automatic_tax: { enabled: taxConfig.applyTax },
    tax_id_collection: { enabled: taxConfig.collectVatId },
    // customer_update allows Stripe Tax to collect a billing address
    customer_update: { address: 'auto', name: 'auto' },
    success_url: `${env.APP_URL}/checkout/success?session_id={CHECKOUT_SESSION_ID}`,
    cancel_url:  `${env.APP_URL}/checkout/cancel`,
    metadata: { inferredCountry: req.headers.get('CF-IPCountry') ?? '' },
  });

  return Response.json({ url: session.url });
}
```

`tax_id_collection` presents a VAT/GST number field on the Checkout
page. If the customer supplies a valid EU VAT ID, Stripe Tax applies
the reverse charge mechanism (0% rate for B2B cross-border EU sales)
automatically.

## EU VAT OSS (One Stop Shop)

EU VAT OSS replaced MOSS from July 2021. Under OSS:
- A single registration in one EU member state covers all EU sales.
- The threshold is €10 000 total EU digital-services revenue per year;
  below this threshold you may apply your home country's rate.
- Stripe Tax calculates per-country rates automatically once you
  register each EU member state in Stripe Dashboard → Tax → Registrations.

```typescript
// Verify the tax amount on a completed Checkout Session
async function onCheckoutCompleted(
  session: Stripe.Checkout.Session, env: Env) {

  const stripe = new Stripe(env.STRIPE_SECRET_KEY);
  // Expand tax details
  const full = await stripe.checkout.sessions.retrieve(session.id, {
    expand: ['total_details.breakdown.taxes'],
  });

  const taxes = full.total_details?.breakdown?.taxes ?? [];
  for (const t of taxes) {
    // t.amount = tax in cents; t.rate.jurisdiction, t.rate.percentage
    console.log(
      `Tax: ${t.amount} ${session.currency?.toUpperCase()} ` +
      `(${t.rate.percentage}% ${t.rate.display_name} ` +
      `– ${t.rate.jurisdiction})`
    );
  }
}
```

## PaymentIntent path (non-Checkout)

For mobile apps that build their own payment UI with Stripe Elements:

```typescript
async function createPaymentIntentWithTax(
  customerId: string, priceId: string,
  env: Env, countryCode: string
): Promise<Stripe.PaymentIntent> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY);

  // 1. Retrieve price to get amount
  const price = await stripe.prices.retrieve(priceId);
  const amount = price.unit_amount!;

  // 2. Calculate tax preview (optional, for display before payment)
  const taxCalc = await stripe.tax.calculations.create({
    currency:      price.currency,
    line_items:    [{ amount, reference: priceId, quantity: 1 }],
    customer_details: {
      address: { country: countryCode },
      address_source: 'billing',
    },
    expand: ['line_items'],
  });

  // 3. Create PaymentIntent referencing the Tax Calculation
  const pi = await stripe.paymentIntents.create({
    amount:      taxCalc.amount_total,
    currency:    taxCalc.currency,
    customer:    customerId,
    automatic_tax: { enabled: true },
    metadata: {
      tax_calculation: taxCalc.id,
      priceId,
    },
  });

  return pi;
}
```

The `stripe.tax.calculations.create` call returns the tax-inclusive
total before the PaymentIntent is created — send `taxCalc.tax_amount_exclusive`
and `taxCalc.amount_total` to the mobile client for display.

## Mobile checkout tax display

Mobile clients should display tax before confirming:

```typescript
// Response shape sent to mobile app
interface CheckoutPreview {
  subtotal:     number;  // cents, before tax
  taxAmount:    number;  // cents
  taxLabel:     string;  // "VAT (20%)" / "GST (10%)" / "Sales Tax"
  total:        number;  // cents
  currency:     string;
  taxBreakdown: TaxLine[];
}

interface TaxLine {
  label:      string;
  rate:       number;   // percentage
  amount:     number;   // cents
  jurisdiction: string;
}
```

Construct from `taxCalc.line_items.data[0].tax_breakdown` — each entry
has `tax_rate_details.display_name`, `tax_rate_details.percentage_decimal`,
and `amount`. Pass this to the mobile UI before the user taps Pay.

## Registration workflow in Stripe Dashboard

Before tax is applied in any jurisdiction, example project must add a
registration in Stripe Dashboard → Tax → Registrations:

| Jurisdiction | Registration type       | Notes                        |
|--------------|-------------------------|------------------------------|
| EU (OSS)     | One Stop Shop (OSS)     | Single filing covers all EU  |
| GB           | Standard VAT            | UK VAT registration required |
| AU           | Standard GST            | ABN required                 |
| US states    | State Sales Tax         | Nexus triggers registration  |
| CA           | GST/HST or PST          | Province-specific            |

Add each registration before enabling `automatic_tax` for customers
in that jurisdiction. Stripe Tax silently skips tax for jurisdictions
with no active registration — no error is thrown.

## Anti-patterns

- Using `CF-IPCountry` as the definitive tax jurisdiction — it is
  an IP-level hint only; billing address collected at Checkout
  overrides it. Stripe Tax uses the billing address.
- Enabling `automatic_tax: { enabled: true }` without any active
  registrations — Stripe calculates 0% for all customers silently.
- Creating the PaymentIntent with a hard-coded `amount` and then
  adding `automatic_tax` — the PaymentIntent amount is what gets
  charged; Stripe Tax adjusts the final charge to `amount_total`
  from the calculation, but only if the amount was set correctly.
- Skipping `customer_update: { address: 'auto' }` on Checkout — the
  customer's address stays blank and Stripe Tax cannot run.
- Collecting a VAT ID but not passing `tax_id_collection: { enabled: true }` —
  the field never appears on the Checkout page.

## Gotchas

- `stripe.tax.calculations.create` is a **read** operation and is free;
  `stripe.tax.transactions.create` records the transaction and counts
  toward filing — call it only after payment succeeds.
- Stripe Tax requires the customer's **country** at minimum; region,
  postal code, and city improve US sales-tax accuracy (ZIP+4 routing).
- OSS filings must be submitted per-quarter by the 20th of the month
  following the quarter end (e.g. Q1 ending 31 March → file by 20 April).
- Stripe Tax does not file returns on your behalf — it provides data;
  use Stripe Tax Reports (Dashboard → Tax → Reports) to export per-country
  collected amounts for your accountant.
- `tax_id_collection` is available only on Checkout Sessions and
  Subscriptions; it is not available on direct PaymentIntents.

## Verification checklist

- Create a Checkout Session with `automatic_tax: { enabled: true }` and
  a German customer address; confirm `total_details.amount_tax` is 19%
  of the line item amount.
- Supply a valid DE VAT ID; confirm tax rate drops to 0% (reverse charge).
- Set `CF-IPCountry: AU` in a test request; confirm `collectVatId: false`
  and `displayHint` references GST.
- Set `CF-IPCountry: XX`; confirm fallback to default tax config
  without throwing.
- Run `stripe.tax.calculations.create` with `country: US` and a ZIP
  code in California; verify a positive tax amount is returned.

## Related

- `payments/stripe-tax-calculation.md`
- `payments/stripe-tax-customer-location-evidence.md`
- `payments/vat-calculation-eu.md`
- `payments/sales-tax-us-states.md`
- `payments/stripe-checkout-session.md`

## Source URLs (verified 2026-08-22)

- https://docs.stripe.com/tax/set-up
- https://docs.stripe.com/tax/calculations
- https://docs.stripe.com/api/tax/calculations/create
- https://docs.stripe.com/tax/checkout
- https://docs.stripe.com/tax/registrations
- https://ec.europa.eu/taxation_customs/business/vat/telecommunications-broadcasting-electronic-services/oss_en
- https://developers.cloudflare.com/fundamentals/reference/http-request-headers/
