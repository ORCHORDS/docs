# Embedded Finance with Stripe Treasury on Cloudflare Workers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Marketplace and vertical SaaS platforms want to offer users their own spending accounts, virtual cards, and money movement features without building a full banking stack. Stripe Treasury and Stripe Issuing provide the regulated financial infrastructure; Cloudflare Workers handles API orchestration, webhook fan-out, and compliance-gating at the edge.

## Context

Stripe Treasury lets Connect platforms provision FDIC-insured financial accounts (`FinancialAccount`) for each connected account. Stripe Issuing mints virtual cards backed by those balances. All money-movement operations (fund flows, payouts, card spend) emit webhook events that your platform must process durably. Workers serve as the thin orchestration layer between your product surface and Stripe's financial APIs, while Cloudflare Queues ensures webhook delivery survives transient downstream failures.

## Provisioning Financial Accounts and KYC Gating

A financial account can only be created for a fully verified Connect account. Workers enforce this gate before calling Stripe Treasury.

```typescript
// src/treasury/provision.ts
import Stripe from 'stripe';

export async function provisionFinancialAccount(
  connectedAccountId: string,
  env: Env,
): Promise<Stripe.Treasury.FinancialAccount> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY);

  // Gate on KYC verification status
  const account = await stripe.accounts.retrieve(connectedAccountId);
  if (
    account.requirements?.disabled_reason ||
    !account.charges_enabled ||
    !account.payouts_enabled
  ) {
    throw new Error(
      `Account ${connectedAccountId} is not fully verified; ` +
        `cannot provision a financial account.`,
    );
  }

  const fa = await stripe.treasury.financialAccounts.create(
    {
      supported_currencies: ['usd'],
      features: {
        card_issuing: { requested: true },
        deposit_insurance: { requested: true },
        financial_addresses: { aba: { requested: true } },
        inbound_transfers: { ach: { requested: true } },
        intra_stripe_flows: { requested: true },
        outbound_payments: {
          ach: { requested: true },
          us_domestic_wire: { requested: true },
        },
        outbound_transfers: { ach: { requested: true } },
      },
    },
    { stripeAccount: connectedAccountId },
  );

  // Persist mapping in D1
  await env.DB.prepare(
    `INSERT OR REPLACE INTO financial_accounts
       (connected_account_id, financial_account_id, status, created_at)
     VALUES (?, ?, ?, unixepoch())`,
  )
    .bind(connectedAccountId, fa.id, fa.active_features.join(','))
    .run();

  return fa;
}
```

## Issuing Virtual Cards and Balance Inquiries

Cards are issued against the financial account's balance. Workers expose a thin REST surface so your frontend can request cards and check available funds.

```typescript
// src/treasury/cards.ts
import Stripe from 'stripe';

export async function issueVirtualCard(
  connectedAccountId: string,
  cardholderId: string,
  financialAccountId: string,
  spendingLimitCents: number,
  env: Env,
): Promise<Stripe.Issuing.Card> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY);

  const card = await stripe.issuing.cards.create(
    {
      cardholder: cardholderId,
      currency: 'usd',
      type: 'virtual',
      financial_account: financialAccountId,
      spending_controls: {
        spending_limits: [
          { amount: spendingLimitCents, interval: 'monthly' },
        ],
      },
      status: 'active',
    },
    { stripeAccount: connectedAccountId },
  );

  await env.DB.prepare(
    `INSERT INTO issued_cards
       (card_id, connected_account_id, cardholder_id, financial_account_id,
        spend_limit_cents, status, created_at)
     VALUES (?, ?, ?, ?, ?, 'active', unixepoch())`,
  )
    .bind(
      card.id,
      connectedAccountId,
      cardholderId,
      financialAccountId,
      spendingLimitCents,
    )
    .run();

  return card;
}

export async function getBalance(
  connectedAccountId: string,
  financialAccountId: string,
  env: Env,
): Promise<{ available: number; inboundPending: number; outboundPending: number }> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY);
  const fa = await stripe.treasury.financialAccounts.retrieve(
    financialAccountId,
    { stripeAccount: connectedAccountId },
  );
  return {
    available: fa.balance.cash.usd,
    inboundPending: fa.balance.inbound_pending.usd,
    outboundPending: fa.balance.outbound_pending.usd,
  };
}
```

## Webhook Processing for Financial Events via Queues

Treasury emits high-volume events (card authorisations, inbound/outbound transfers, transaction entries). A Worker verifies the signature and immediately enqueues the event; a separate consumer processes it durably without blocking the HTTP response to Stripe.

```typescript
// src/treasury/webhooks.ts
import Stripe from 'stripe';

export async function handleTreasuryWebhook(
  request: Request,
  env: Env,
): Promise<Response> {
  const sig = request.headers.get('stripe-signature') ?? '';
  const body = await request.text();

  let event: Stripe.Event;
  try {
    const stripe = new Stripe(env.STRIPE_SECRET_KEY);
    event = await stripe.webhooks.constructEventAsync(
      body,
      sig,
      env.STRIPE_TREASURY_WEBHOOK_SECRET,
    );
  } catch {
    return new Response('Bad signature', { status: 400 });
  }

  // Idempotency check before enqueue
  const existing = await env.DB.prepare(
    'SELECT 1 FROM processed_events WHERE event_id = ?',
  )
    .bind(event.id)
    .first();

  if (!existing) {
    await env.TREASURY_QUEUE.send({ event });
    await env.DB.prepare(
      `INSERT INTO processed_events (event_id, event_type, received_at)
       VALUES (?, ?, unixepoch())`,
    )
      .bind(event.id, event.type)
      .run();
  }

  return new Response('ok');
}

// Queue consumer
export async function treasuryConsumer(
  batch: MessageBatch<{ event: Stripe.Event }>,
  env: Env,
): Promise<void> {
  for (const message of batch.messages) {
    const { event } = message.body;

    switch (event.type) {
      case 'treasury.transaction.created': {
        const txn = event.data.object as Stripe.Treasury.Transaction;
        await env.DB.prepare(
          `INSERT OR IGNORE INTO treasury_transactions
             (txn_id, financial_account_id, amount, currency, flow_type, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)`,
        )
          .bind(
            txn.id,
            txn.financial_account,
            txn.amount,
            txn.currency,
            txn.flow_type,
            txn.status,
            txn.created,
          )
          .run();
        break;
      }
      case 'issuing.authorization.created': {
        const auth = event.data.object as Stripe.Issuing.Authorization;
        // Real-time spend controls: reject if over merchant category policy
        const stripe = new Stripe(env.STRIPE_SECRET_KEY);
        const connectedAccountId = (event.account as string) ?? '';
        if (auth.merchant_data.category === 'gambling') {
          await stripe.issuing.authorizations.decline(auth.id, {
            stripeAccount: connectedAccountId,
          });
        } else {
          await stripe.issuing.authorizations.approve(auth.id, {
            stripeAccount: connectedAccountId,
          });
        }
        break;
      }
    }

    message.ack();
  }
}
```

## Anti-patterns

- Exposing the connected account's raw Stripe secret key to the frontend to call Treasury APIs directly — all money-movement must be server-side in Workers where secrets are environment variables.
- Provisioning financial accounts before KYC is complete; Stripe will create the account object but freeze features until verification passes, and customers see confusing "account restricted" errors.
- Processing `issuing.authorization.created` synchronously inside the webhook handler — Stripe's real-time authorisation webhook has a 2-second response window; enqueue immediately and process in a separate consumer only for non-blocking use cases; for spend-control decisions approve/decline inline.

## Gotchas

- Stripe Treasury is a regulated product requiring platform-level approval; submit the Treasury application in the Dashboard before calling any `treasury.*` API — unapproved platforms receive `permission_error`.
- `FinancialAccount.balance.cash` reflects settled funds only; card spend authorisations reduce `outbound_pending` but do not hit `cash` until the transaction is captured (T+1 for most card networks).

## Verification

```bash
# Create a test financial account against a test-mode Connect account
curl https://api.stripe.com/v1/treasury/financial_accounts \
  -u "$STRIPE_SECRET_KEY:" \
  -H "Stripe-Account: acct_test_connected" \
  -d "supported_currencies[]=usd" \
  -d "features[card_issuing][requested]=true"

# Check D1 for provisioned accounts
wrangler d1 execute example project-db \
  --command "SELECT * FROM financial_accounts ORDER BY created_at DESC LIMIT 5;"

# Tail treasury webhook consumer
wrangler tail --format=pretty --search treasury
```

## Related

- `payments/stripe-connect-platform.md`
- `payments/stripe-identity-kyc-payment-gating.md`
- `payments/stripe-issuing-real-time-authorization-webhooks.md`
- `payments/embedded-finance-banking-as-a-service.md`
- `payments/stripe-treasury-transaction-entry-reconciliation.md`

## Sources

- https://stripe.com/docs/treasury
- https://stripe.com/docs/issuing
- https://stripe.com/docs/connect
- https://developers.cloudflare.com/queues/
- https://stripe.com/docs/treasury/compliance
