# Embedded Finance — Banking as a Service (BaaS) Integration Engineering

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your SaaS platform processes payments through Stripe but customers want
to hold balances, issue cards to their employees, and send payouts —
all without leaving your application. You consider becoming a bank or
money services business but the licensing takes 12-24 months and
millions in compliance costs. Your users switch to competitors who
offer financial features natively. You need to embed banking, lending,
or card issuance into your product without becoming a regulated
financial institution yourself.

## Context

Embedded finance is the integration of financial services (payments,
accounts, cards, lending, insurance) directly into non-bank software
products via APIs. Banking as a Service (BaaS) is the infrastructure
layer that makes this possible — licensed banks and fintechs expose
their regulated capabilities through APIs, allowing platforms to offer
financial products under their own brand. In 2026, the embedded finance
market generates approximately $320 billion in revenue. Key providers
include Stripe Treasury and Issuing, Unit, Marqeta, Adyen for
Platforms, and Column. Regulatory scrutiny has intensified since 2024
(Synapse collapse, OCC/FDIC guidance on bank-fintech partnerships),
requiring clear compliance ownership, ledger integrity, and third-party
risk management in every integration.

## Architecture

```
Embedded Finance Stack:

┌─────────────────────────────────────────┐
│         Your Platform (UI/UX)           │
│   Accounts · Cards · Payments · Lending │
└────────────────┬────────────────────────┘
                 │ API calls
┌────────────────▼────────────────────────┐
│         BaaS Provider (middleware)       │
│   Stripe Treasury · Unit · Column        │
│   KYC/KYB · Ledger · Card processing    │
└────────────────┬────────────────────────┘
                 │ Banking rails
┌────────────────▼────────────────────────┐
│         Partner Bank (license holder)    │
│   FBO accounts · FDIC insurance          │
│   ACH · Wire · Card network access       │
└──────────────────────────────────────────┘

FBO (For Benefit Of) structure:
  Partner bank holds one omnibus account
  BaaS provider maintains sub-ledger per end user
  Each sub-ledger balance is FDIC-insured (up to $250K)
```

## BaaS provider comparison

```
Stripe Treasury + Issuing:
  → Financial accounts with ACH, wire, check
  → Virtual and physical card issuance
  → Built on Stripe Connect (extend existing integration)
  → Partner banks: Goldman Sachs, Evolve
  → Best for: existing Stripe platforms

Unit:
  → Full BaaS: accounts, cards, ACH, wires, checks
  → White-label banking experience
  → Built-in KYC/KYB, transaction monitoring
  → Partner bank: Blue Ridge Bank
  → Best for: neobank-style products

Marqeta:
  → Card issuance and processing specialist
  → Just-in-time (JIT) funding for card authorization
  → Virtual, physical, tokenized cards
  → Used by: Square Cash, DoorDash, Instacart
  → Best for: card-centric programs

Column:
  → Developer bank (actual bank with API-first model)
  → Direct bank relationship (no middleware)
  → ACH, wire, FedNow, card issuance
  → Best for: fintechs wanting direct bank access

Adyen for Platforms:
  → Payments + embedded financial products
  → Sub-accounts, split payments, issuing
  → Global coverage (40+ countries)
  → Best for: international marketplaces
```

## Stripe Treasury integration

```javascript
// Create a financial account for a connected account
const financialAccount = await stripe.treasury.financialAccounts.create(
  {
    supported_currencies: ['usd'],
    features: {
      deposit_insurance: { requested: true },
      financial_addresses: { aba: { requested: true } },
      inbound_transfers: { ach: { requested: true } },
      outbound_payments: {
        ach: { requested: true },
        us_domestic_wire: { requested: true },
      },
      outbound_transfers: {
        ach: { requested: true },
        us_domestic_wire: { requested: true },
      },
    },
  },
  { stripeAccount: 'acct_connected_123' }
);

// Send money from financial account via ACH
const outboundPayment = await stripe.treasury.outboundPayments.create(
  {
    financial_account: financialAccount.id,
    amount: 50000, // $500.00
    currency: 'usd',
    destination_payment_method_data: {
      type: 'us_bank_account',
      us_bank_account: {
        routing_number: '110000000',
        account_number: '000123456789',
        account_holder_type: 'individual',
        financial_connections_account: 'fca_xxx',
      },
    },
    description: 'Vendor payment',
  },
  { stripeAccount: 'acct_connected_123' }
);

// Issue a card for a connected account
const card = await stripe.issuing.cards.create(
  {
    cardholder: 'ich_cardholder_123',
    type: 'virtual',
    currency: 'usd',
    spending_controls: {
      spending_limits: [
        { amount: 100000, interval: 'monthly' }, // $1,000/month
      ],
      allowed_categories: ['travel', 'office_supplies'],
    },
  },
  { stripeAccount: 'acct_connected_123' }
);
```

## KYC/KYB integration

```
Know Your Customer (individuals):
  → Identity verification (government ID + selfie)
  → Address verification
  → SSN/TIN verification
  → OFAC/sanctions screening
  → PEP (Politically Exposed Person) check

Know Your Business (companies):
  → Business registration verification
  → Beneficial ownership identification
  → UBO (Ultimate Beneficial Owner) verification
  → Industry/risk classification
  → Ongoing monitoring and periodic review

Providers:
  → Stripe Identity: built-in, simplest for Stripe users
  → Alloy: orchestration across multiple data sources
  → Persona: identity verification platform
  → Sardine: fraud + compliance in one
  → Unit21: transaction monitoring and case management
```

## Compliance requirements

```
BSA/AML (Bank Secrecy Act / Anti-Money Laundering):
  → Transaction monitoring for suspicious activity
  → SAR (Suspicious Activity Report) filing
  → CTR (Currency Transaction Report) for >$10,000
  → Customer Due Diligence (CDD) program

Regulatory oversight:
  → OCC/FDIC third-party risk management guidance
  → Bank partner responsible for compliance program
  → Platform must cooperate with bank's compliance team
  → Regular audits of platform's KYC/AML processes

State money transmitter licenses:
  → May be required depending on fund flow structure
  → Bank partnership typically provides regulatory cover
  → Consult fintech legal counsel for your specific model

Data security:
  → PCI DSS for card data
  → SOC 2 Type II for platform
  → GLBA (Gramm-Leach-Bliley Act) for financial data
  → Encryption at rest and in transit
```

## Anti-patterns

- **Ignoring ledger reconciliation** — assuming the BaaS provider's
  ledger is always correct. Implement daily reconciliation between
  your internal records and the BaaS provider's ledger. Discrepancies
  must be flagged and resolved before they compound.
- **Building without a bank partner strategy** — relying on a
  single BaaS provider without understanding the underlying bank
  relationship. The Synapse collapse (2024) showed that platform
  customers can lose access to funds when the middleware layer
  fails. Understand your bank partner and have contingency plans.
- **Skipping transaction monitoring** — leaving all compliance to
  the bank partner. Regulators expect platforms to have their own
  transaction monitoring and suspicious activity detection. This is
  especially critical for marketplace and gig-economy platforms.
- **Treating embedded finance as just another API** — financial
  product integrations carry regulatory obligations that typical
  SaaS APIs do not. Every feature (accounts, cards, lending) has
  specific compliance requirements. Engage fintech legal counsel
  before launching.

## Gotchas

- **FDIC insurance limits** — FBO accounts are FDIC-insured up to
  $250,000 per end user, but only if the bank maintains proper
  records identifying each beneficial owner. If records are
  inadequate, insurance may not pass through to end users.
- **Regulatory changes** — OCC and FDIC guidance on bank-fintech
  partnerships is evolving rapidly (2024-2026). What is compliant
  today may require changes next quarter. Budget for ongoing
  regulatory monitoring and adaptation.
- **Webhook reliability for financial events** — payment
  settlements, card authorizations, and account status changes
  arrive via webhooks. Missing a webhook can mean missed
  transactions, incorrect balances, or failed card authorizations.
  Implement idempotent processing and reconciliation sweeps.
- **Multi-state compliance** — if your platform operates across US
  states, money transmitter licensing requirements vary. Your bank
  partnership structure determines whether you need your own
  licenses. Get a legal opinion specific to your fund flow model.

## Verification

- BaaS provider integration handles account creation, funding, and payouts.
- KYC/KYB verification completes before financial account activation.
- Transaction monitoring detects suspicious patterns.
- Daily reconciliation runs between platform ledger and BaaS provider.
- Card spending controls enforce per-card and per-cardholder limits.
- Webhook processing is idempotent with reconciliation fallback.
- Bank partner relationship and contingency plan are documented.

## Related

- `documentation/docs/policies/payments/payment-orchestration-layer-routing.md`
- `documentation/docs/policies/payments/stripe-connect-platform.md`
- `documentation/docs/policies/payments/pci-dss-scope-reduction.md`

## Source URLs (verified 2026-08-16)

- Embedded Finance vs Banking as a Service in 2026 — https://www.techrepublic.com/article/embedded-finance-vs-banking-as-a-service/
- Banking as a Service (BaaS): Architecture, Use Cases, PSD3 — https://crassula.io/solutions/embedded-finance/guides/banking-as-a-service/
- Stripe Embedded Finance Integration Guide — https://docs.stripe.com/baas/start-integration/integration-guides/embedded-finance
- Embedded Finance and BaaS: 2026 Institutional Outlook — https://sumsub.com/blog/banking-as-a-service/
