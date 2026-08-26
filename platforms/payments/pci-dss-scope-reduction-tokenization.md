# PCI DSS Scope Reduction via Tokenization

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A security audit questions whether the platform is in scope for
PCI DSS, which would require a full QSA assessment. Engineering
needs to confirm that card data never touches WAM servers and
that our Self-Assessment Questionnaire (SAQ) tier is correct.

## Context

example.com collects payments through Stripe Elements (web) and
the Stripe iOS/Android SDK (mobile). Card numbers are never
typed into a field hosted on our domain or processed by our
Cloudflare Workers. Our backend only handles Stripe tokens and
PaymentIntent IDs, which are not considered cardholder data.

## 1. Cardholder Data Environment (CDE) Definition

The CDE is any system that stores, processes, or transmits
Primary Account Numbers (PAN), sensitive authentication data
(CVV/CVC, PIN), or cardholder names paired with account data.

```
┌──────────────────────────────────────────────────────────┐
│                  WAM Payment Architecture                │
├──────────────┬───────────────────────────────────────────┤
│ IN scope      │ OUT of scope                             │
│ (CDE)         │                                          │
├──────────────┼───────────────────────────────────────────┤
│ Stripe infra  │ api.example.com (Workers)                 │
│               │ D1 — stores only stripe_customer_id,     │
│               │   payment_intent_id, last4, card_brand   │
│               │ KV — velocity counters, session tokens   │
│               │ R2 — media assets only                   │
└──────────────┴───────────────────────────────────────────┘
```

`last4` and `card_brand` are explicitly out of scope under PCI
DSS 4.0 section 3.2 — they are not sufficient to reconstruct
the PAN.

## 2. SAQ A Eligibility

SAQ A applies when:
1. All payment pages are fully outsourced to a PCI-compliant
   provider (Stripe).
2. No cardholder data is retained, processed, or transmitted
   by the merchant's systems.
3. Card entry fields are served from the provider's domain via
   iframe or redirect.

Stripe Elements loads its iframe from `js.stripe.com`. Our
page never touches the DOM inside that iframe. This satisfies
SAQ A requirements. SAQ A has 22 requirements vs 329 for SAQ D
— the scope reduction is material.

To maintain SAQ A compliance:
- Never add custom JS that reads from the Stripe iframe.
- Never proxy Stripe API calls through our own backend if they
  involve raw card data.
- Never log `payment_method` details beyond token ID.

Request Stripe's PCI DSS 4.0 compliance letter from the
Dashboard under Settings → Compliance; attach it to the
annual merchant questionnaire.

## 3. Payment Tokenization vs Network Tokenization

These are two distinct mechanisms, often confused:

```
┌─────────────────────┬────────────────────────────────────┐
│ Payment Tokenization│ Network Tokenization               │
├─────────────────────┼────────────────────────────────────┤
│ Stripe replaces PAN │ Card schemes (Visa/MC/Amex) issue  │
│ with a pm_xxx token │ a network token (DPAN) per device  │
│ Stored in our D1    │ Managed by Stripe internally       │
│ Used in Workers API │ Used in authorization to issuer    │
│ Scope reduction only│ Scope reduction + better auth rates│
└─────────────────────┴────────────────────────────────────┘
```

Payment tokenization keeps us out of scope. Network
tokenization (below) adds conversion and cost benefits on top.

## 4. Stripe Elements — PCI DSS 4.0 Scope Reduction

Stripe Elements (v3+) injects a sandboxed iframe served from
`js.stripe.com` for card input. Our Content-Security-Policy
must allow it without widening scope:

```
# Cloudflare Worker — set via response headers
Content-Security-Policy:
  default-src 'self';
  script-src 'self' https://js.stripe.com;
  frame-src https://js.stripe.com;
  connect-src 'self' https://api.stripe.com;
  img-src 'self' data:;
  style-src 'self' 'unsafe-inline';
```

Do not add `frame-src *` — it opens clickjacking vectors and
may void the SAQ A self-certification.

Stripe's integration guide mandates loading the Stripe.js
library directly from `https://js.stripe.com/v3/` and not
self-hosting it. Bundling Stripe.js removes Stripe's ability
to apply real-time fraud signals.

## 5. Network Token Benefits

Stripe enables network tokenization automatically for eligible
cards when the `network_token` feature is active on your account.
Benefits observed in production:

```
┌──────────────────────────┬───────────┬────────────────────┐
│ Metric                   │ PAN-based │ Network token      │
├──────────────────────────┼───────────┼────────────────────┤
│ Authorization rate       │ baseline  │ +2–4 pp            │
│ Interchange rate         │ standard  │ reduced on Visa/MC │
│ Card-on-file fraud rate  │ baseline  │ −20–30 %           │
│ Account updater needed   │ yes       │ no (auto-rotates)  │
└──────────────────────────┴───────────┴────────────────────┘
```

Stripe network tokens are enabled per connected account. For
our Express accounts, Stripe manages token provisioning
transparently. No code change is required; verify in Dashboard
under Settings → Card settings → Network tokens.

## 6. Cardholder Data Logging Audit

Run this check before every production deploy:

```typescript
// Ensure no card fields leak into Worker logs
function sanitizePaymentLog(data: Record<string, unknown>)
  : Record<string, unknown> {
  const BLOCKED = [
    "number", "cvc", "exp_month", "exp_year",
    "card_number", "cvv", "pan",
  ];
  return Object.fromEntries(
    Object.entries(data).filter(
      ([k]) => !BLOCKED.some((b) =>
        k.toLowerCase().includes(b)),
    ),
  );
}
```

Add a lint rule (e.g. ESLint `no-restricted-syntax`) that
flags any `console.log` or `logflare.send` call whose argument
contains string literals matching `/\bcard\b|\bpan\b|\bcvc\b/i`.

## Anti-patterns

- Self-hosting `stripe.js` — breaks network token provisioning
  and fraud signals; voids PCI scope assurances.
- Logging `PaymentMethod` objects returned by Stripe — they
  contain `card.last4`, `card.exp_month`, and `card.brand`;
  not PAN but a data minimization failure.
- Passing `card[number]` through a server-side proxy "for
  analytics" — immediately puts server in scope for SAQ D.
- Storing `pi_xxx` and `pm_xxx` IDs in the same table column
  named `card_token` — confuses auditors; use distinct columns.

## Gotchas

- PCI DSS 4.0 (effective 2025-03-31) requires `script-src`
  integrity hashes for third-party scripts on payment pages.
  Stripe.js does not publish SRI hashes; use `nonce-{random}`
  instead and document the exception.
- SAQ A covers e-commerce only. If CS agents ever manually
  key card numbers into any internal tool, SAQ A no longer
  applies — use Stripe's virtual terminal instead.
- `last4` stored in D1 is non-sensitive by itself but paired
  with `exp_month` and `exp_year` becomes a partial PAN;
  store only `last4` + `brand`, never expiry.
- Network tokens do not help with 3DS liability shift — that
  is governed by the 3DS flow, not the token type.

## Verification

```bash
# Confirm no PAN-shaped data in Worker logs (regex: 4-digit groups)
wrangler tail --format json 2>/dev/null \
  | jq -r '.logs[].message[]' \
  | grep -E '\b[0-9]{4}[- ]?[0-9]{4}[- ]?[0-9]{4}[- ]?[0-9]{4}\b' \
  | wc -l
# Expected: 0

# Verify Stripe PCI compliance letter is current
curl -s https://stripe.com/docs/security/stripe \
  | grep -i "pci"
```

Confirm Stripe Dashboard → Settings → Compliance shows
"PCI DSS 4.0 — SAQ A" with no outstanding action items.

## Related

- `payment-fraud-detection-velocity-checks.md`
- `stripe-connect-marketplace-platform-payments.md`
- `crypto-payments-nowpayments-settlement.md`

## Source URLs (verified 2026-08-17)

- https://stripe.com/docs/security/guide
- https://stripe.com/docs/payments/payment-card-industry
- https://www.pcisecuritystandards.org/document_library/
- https://stripe.com/docs/network-tokens
- https://stripe.com/docs/js/including
