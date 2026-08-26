# Stripe Pricing Table Embed Widget

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

You need a pricing page that stays in sync with your Stripe products and prices without a custom-built React component. Updating pricing should not require a code deployment. Stripe's `<stripe-pricing-table>` web component reads directly from the Stripe dashboard, renders plan cards, handles currency localization, and redirects to Checkout — all with a single script tag and two attributes. The complexity appears when you need to pre-fill customer data, pass metadata through to subscriptions, restrict which prices are shown to which users, or integrate with an existing auth session.

## Context

`<stripe-pricing-table>` is a Custom Element (Web Component) served from Stripe's CDN. It renders server-side via Stripe's own infrastructure and communicates back using a postMessage bridge. It does not require Stripe.js to be loaded separately.

The widget supports:
- Multiple pricing options (monthly/annual toggle built-in)
- Automatic currency display based on customer locale
- Passing a pre-created Customer ID (`customer-id`) to associate the checkout
- Passing a `client-reference-id` threaded through to the Checkout session
- Configuring trial periods per price in the dashboard
- Custom domains (for Stripe-hosted pages) — the embed still loads from `js.stripe.com`

The widget **does not** support dynamic plan filtering per user, complex discount logic visible before checkout, or multi-step flows — for those, build a custom Checkout or Elements integration.

## Basic Embed

The simplest case: paste the embed code generated in the Stripe Dashboard under Products → Pricing Table.

```html
<!-- pricing.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Plans</title>
  <!-- Load the web component script once per page -->
  <script async src="https://js.stripe.com/v3/pricing-table.js"></script>
</head>
<body>
  <!--
    pricing-table-id: copy from Stripe Dashboard > Products > Pricing tables
    publishable-key: your pk_live_xxx or pk_test_xxx key
  -->
  <stripe-pricing-table
    pricing-table-id="prctbl_xxx"
    publishable-key="pk_live_xxx"
  ></stripe-pricing-table>
</body>
</html>
```

Both attributes are **required**. The component renders asynchronously — it fetches the pricing table config from Stripe's API using the publishable key. There is no skeleton / loading state emitted by the component itself; add a CSS placeholder if needed.

## Passing an Existing Customer ID

When the user is already logged in and has a Stripe customer record, pass `customer-id` to pre-fill their email in Checkout and associate the new subscription with the existing customer. This prevents duplicate customer creation.

```typescript
// workers/pricing-page.ts — server-side render for an authenticated user

export async function handlePricingPage(
  request: Request,
  env: Env
): Promise<Response> {
  // Resolve the logged-in user's Stripe customer ID
  const session = await getSession(request, env);
  if (!session) {
    return Response.redirect("/login?next=/pricing", 302);
  }

  const customerId = await resolveStripeCustomer(
    session.userId,
    env.DB,
    env.STRIPE_SECRET_KEY
  );

  const html = `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Choose a Plan</title>
  <script async src="https://js.stripe.com/v3/pricing-table.js"></script>
</head>
<body>
  <stripe-pricing-table
    pricing-table-id="${env.STRIPE_PRICING_TABLE_ID}"
    publishable-key="${env.STRIPE_PUBLISHABLE_KEY}"
    customer-id="${customerId}"
  ></stripe-pricing-table>
</body>
</html>`;

  return new Response(html, {
    headers: { "Content-Type": "text/html;charset=UTF-8" },
  });
}

async function resolveStripeCustomer(
  userId: string,
  db: D1Database,
  stripeKey: string
): Promise<string> {
  const row = await db
    .prepare(`SELECT stripe_customer_id FROM users WHERE id = ?`)
    .bind(userId)
    .first<{ stripe_customer_id: string | null }>();

  if (row?.stripe_customer_id) return row.stripe_customer_id;

  // Create a new customer and persist
  const stripe = new (await import("stripe")).default(stripeKey);
  const userRow = await db
    .prepare(`SELECT email, name FROM users WHERE id = ?`)
    .bind(userId)
    .first<{ email: string; name: string }>();

  const customer = await stripe.customers.create({
    email: userRow!.email,
    name: userRow!.name,
    metadata: { app_user_id: userId },
  });

  await db
    .prepare(`UPDATE users SET stripe_customer_id = ? WHERE id = ?`)
    .bind(customer.id, userId)
    .run();

  return customer.id;
}
```

## Passing Metadata and Client Reference ID

`client-reference-id` passes a string (up to 200 chars) through to the Checkout session's `client_reference_id` field. Use it to correlate the checkout back to your internal user, order, or campaign.

```html
<!-- Use a server-rendered template to inject the user ID -->
<stripe-pricing-table
  pricing-table-id="prctbl_xxx"
  publishable-key="pk_live_xxx"
  customer-id="cus_xxx"
  client-reference-id="usr_abc123"
></stripe-pricing-table>
```

In a Cloudflare Worker with HTMLRewriter, inject the attribute dynamically without building a full HTML string:

```typescript
// workers/pricing-rewriter.ts
export async function injectPricingAttributes(
  response: Response,
  userId: string,
  customerId: string
): Promise<Response> {
  return new HTMLRewriter()
    .on("stripe-pricing-table", {
      element(el) {
        el.setAttribute("customer-id", customerId);
        el.setAttribute("client-reference-id", userId);
      },
    })
    .transform(response);
}
```

Listen for `checkout.session.completed` on your webhook endpoint and use `client_reference_id` to provision access:

```typescript
// workers/checkout-webhook.ts
import Stripe from "stripe";

export async function handleCheckoutComplete(
  event: Stripe.Event,
  db: D1Database
): Promise<void> {
  if (event.type !== "checkout.session.completed") return;
  const session = event.data.object as Stripe.Checkout.Session;

  const userId = session.client_reference_id;
  const customerId = session.customer as string;
  const subscriptionId = session.subscription as string;

  if (!userId || !subscriptionId) return;

  await db
    .prepare(
      `UPDATE users
       SET stripe_customer_id = ?,
           stripe_subscription_id = ?,
           plan_status = 'active',
           updated_at = ?
       WHERE id = ?`
    )
    .bind(customerId, subscriptionId, new Date().toISOString(), userId)
    .run();
}
```

## Customizing Appearance via Dashboard

The Stripe Pricing Table visual style is configured entirely in the Stripe Dashboard (no CSS injection from the embed side). Available controls:

- Font family (limited to Google Fonts subset)
- Primary color (applied to CTAs, highlighted plan border)
- Background color
- Whether to show the annual/monthly toggle
- Which plan to visually highlight ("most popular" badge)
- Button text per plan
- Feature list items per price

To update copy or pricing without a code deployment: edit the pricing table in the Dashboard. Changes propagate to the embed within seconds — no redeploy needed.

**What you cannot change via the embed**:
- Feature comparison table layout
- Custom icons per feature
- Pricing table column count (auto-set by number of plans)
- The currency display format (follows browser locale)

## Restricting the Table to a Subset of Plans per User

The standard embed shows all plans in the pricing table. For tiered access (e.g., enterprise customers see additional plans), the only supported pattern is creating **separate pricing tables** in the Dashboard and serving the appropriate `pricing-table-id` per user tier:

```typescript
// workers/select-pricing-table.ts

type UserTier = "free" | "growth" | "enterprise";

const PRICING_TABLE_IDS: Record<UserTier, string> = {
  free: "prctbl_free_upgrade",
  growth: "prctbl_growth_upgrade",
  enterprise: "prctbl_enterprise_upgrade",
};

export function selectPricingTableId(
  userTier: UserTier,
  env: Env
): string {
  return PRICING_TABLE_IDS[userTier] ?? PRICING_TABLE_IDS.free;
}
```

## Anti-patterns

- **Loading `pricing-table.js` multiple times**: The script is idempotent but loading it twice adds unnecessary network overhead. Load it once in `<head>` with `async`.
- **Hardcoding prices in HTML alongside the pricing table**: The widget is the source of truth; displaying separate hardcoded prices that might fall out of sync undermines the whole point of the widget.
- **Passing the secret key as `publishable-key`**: Only `pk_live_xxx` or `pk_test_xxx` keys are safe in the browser. The secret key must never appear in client-side HTML.
- **Expecting the widget to fire JavaScript events**: The web component does not emit DOM events you can listen to. Post-checkout logic must be handled via Stripe webhooks (`checkout.session.completed`), not client-side callbacks.
- **Using the embed for B2B quoting workflows**: The pricing table is designed for self-serve, fixed-price subscriptions. Custom quotes, volume discounts, or multi-step approval flows require a custom integration with Stripe Quotes or Payment Links.

## Gotchas

- The `customer-id` attribute must be a valid Stripe Customer ID (`cus_xxx`) in the same mode (live/test) as the publishable key. Mixing test/live IDs silently fails — the table renders but checkout errors.
- Content Security Policy headers on your page must allow `js.stripe.com` as a script source and `*.stripe.com` as a frame source. The widget renders inside an iframe:
  ```
  Content-Security-Policy: script-src 'self' https://js.stripe.com;
                            frame-src https://js.stripe.com https://hooks.stripe.com;
  ```
- The widget does not support React's strict mode double-invocation — if you mount it inside a React app in development, it may log duplicate-registration warnings. This does not affect production.
- Pricing table changes in the Dashboard invalidate any server-rendered pricing page caches. If you cache the pricing HTML at the edge (Cloudflare Cache API), set a short TTL (60 seconds) or use cache tags tied to your pricing table version.
- The `<stripe-pricing-table>` element must not be nested inside a `<form>` element — the widget manages its own form submission to Checkout and conflicts with parent form semantics.

## Verification

```bash
# Verify the pricing table exists in your account
stripe pricing_tables retrieve prctbl_xxx

# List all pricing tables
stripe pricing_tables list

# Test the checkout flow end-to-end in test mode
# Use pk_test_xxx + prctbl_test_xxx (create a separate test pricing table)
# Fill in card: 4242 4242 4242 4242, any future date, any CVC

# Verify client_reference_id arrives in checkout.session.completed
stripe listen --forward-to localhost:8787/webhook
stripe trigger checkout.session.completed
```

## Related

- `stripe-checkout-session.md` — building custom Checkout sessions
- `stripe-customer-portal.md` — letting customers manage their own subscription
- `stripe-flat-rate-pricing.md` — flat-rate price configuration
- `stripe-tiered-pricing.md` — tiered price configuration
- `stripe-trial-periods.md` — attaching trials to prices
- `stripe-payment-elements.md` — embedding payments directly in your UI

## Sources

- https://stripe.com/docs/payments/checkout/pricing-table
- https://stripe.com/docs/stripe-js/elements/pricing-table
- https://stripe.com/docs/api/pricing_tables
- https://stripe.com/docs/payments/checkout/custom-domains
