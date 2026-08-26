# Stripe Instant Payouts vs Standard Payout Scheduling

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Platform sellers demand same-day access to their earnings rather than waiting the standard 2–7 business-day settlement cycle. Standard Stripe payouts follow a rolling T+2 or T+7 schedule depending on account age, risk profile, and country. Instant Payouts lets eligible connected accounts receive funds in minutes for an additional fee, but eligibility criteria, fee structure, and scheduling mechanics differ substantially from standard payouts. Getting payout timing wrong causes cash-flow surprises for sellers and unnecessary costs for platforms.

## Context

Stripe supports two payout modes on connected accounts:

- **Standard (scheduled) payouts**: Funds accumulate in the Stripe balance over a rolling window (typically 2 business days for cards in the US) then are swept to the bank account on an automatic schedule (daily, weekly, or monthly).
- **Instant Payouts**: On-demand transfer to a supported debit card or bank account, arriving in minutes, with a 1% fee (minimum $0.50, maximum $15) charged to the platform or seller.

Standard payouts have a `delay_days` property that varies by country, currency, and account risk level. For new accounts Stripe starts at a longer delay (often 7 days) and shortens it automatically as the account builds history. New accounts in the US default to a 7-day delay for the first 30 days; after processing sufficient volume with no disputes, Stripe reduces this to 2 business days automatically.

Workers on Cloudflare run the scheduling logic: checking eligibility, estimating arrival, calculating fees, and calling the Stripe API to create or configure payouts.

## Checking Instant Payout Eligibility

Not every connected account qualifies. Requirements: US-only (for instant via debit card), Visa or Mastercard debit card verified through Stripe, available balance > $0, no active account restrictions.

```typescript
// workers/payout-eligibility.ts
import Stripe from "stripe";

export interface PayoutEligibility {
  standardAvailableAt: Date;
  instantAvailable: boolean;
  instantFeePercent: number;
  instantFeeMinCents: number;
  instantFeeMaxCents: number;
  availableBalanceCents: number;
  currency: string;
  delayDays: number;
}

export async function checkPayoutEligibility(
  stripe: Stripe,
  connectedAccountId: string
): Promise<PayoutEligibility> {
  const [balance, account] = await Promise.all([
    stripe.balance.retrieve({ stripeAccount: connectedAccountId }),
    stripe.accounts.retrieve(connectedAccountId),
  ]);

  const usdAvailable = balance.available.find((b) => b.currency === "usd");
  const availableBalanceCents = usdAvailable?.amount ?? 0;

  // Instant payouts require an external debit card that lists "instant"
  // in its available_payout_methods array
  const externalAccounts = account.external_accounts?.data ?? [];
  const instantCard = externalAccounts.find(
    (ea) =>
      ea.object === "card" &&
      (ea as Stripe.Card).available_payout_methods?.includes("instant")
  );

  const instantAvailable = !!instantCard && availableBalanceCents > 0 &&
    !account.requirements?.disabled_reason;

  const payoutSchedule = account.settings?.payouts?.schedule;
  const delayDays = payoutSchedule?.delay_days ?? 2;

  const standardAvailableAt = new Date();
  standardAvailableAt.setDate(standardAvailableAt.getDate() + delayDays);
  // Stripe skips weekends and US bank holidays — add buffer
  while ([0, 6].includes(standardAvailableAt.getDay())) {
    standardAvailableAt.setDate(standardAvailableAt.getDate() + 1);
  }

  return {
    standardAvailableAt,
    instantAvailable,
    instantFeePercent: 0.01,
    instantFeeMinCents: 50,
    instantFeeMaxCents: 1500,
    availableBalanceCents,
    currency: "usd",
    delayDays,
  };
}
```

## Configuring Payout Schedules per Connected Account

Standard payout schedules (daily / weekly / monthly) can be set per connected account via the Accounts API. Platforms often let sellers choose their preferred cadence in a settings UI. The schedule applies only to automatic payouts; manually created payouts are unaffected.

```typescript
// workers/payout-schedule.ts
import Stripe from "stripe";

type ScheduleInterval = "daily" | "weekly" | "monthly";
type WeeklyAnchor =
  | "monday"
  | "tuesday"
  | "wednesday"
  | "thursday"
  | "friday";

interface ScheduleOptions {
  interval: ScheduleInterval;
  weeklyAnchor?: WeeklyAnchor;
  monthlyAnchor?: number; // 1–31; 31 uses last day of month
}

export async function setPayoutSchedule(
  stripe: Stripe,
  connectedAccountId: string,
  options: ScheduleOptions
): Promise<void> {
  const schedule: Stripe.AccountUpdateParams.Settings.Payouts.Schedule = {
    interval: options.interval,
  };

  if (options.interval === "weekly" && options.weeklyAnchor) {
    schedule.weekly_anchor = options.weeklyAnchor;
  }
  if (options.interval === "monthly" && options.monthlyAnchor != null) {
    schedule.monthly_anchor = options.monthlyAnchor;
  }

  await stripe.accounts.update(connectedAccountId, {
    settings: {
      payouts: {
        schedule,
        // When true, Stripe debits the bank if Stripe balance goes negative
        // (refunds, chargebacks exceed revenue). Set false only if you will
        // manually manage negative balances via platform transfers.
        debit_negative_balances: true,
      },
    },
  });
}

// Weekly on Friday:
// await setPayoutSchedule(stripe, "acct_xxx", {
//   interval: "weekly", weeklyAnchor: "friday"
// });

// Monthly on the 1st:
// await setPayoutSchedule(stripe, "acct_xxx", {
//   interval: "monthly", monthlyAnchor: 1
// });
```

## Creating an Instant Payout via Workers

When a seller clicks "Get Paid Now", the Worker validates eligibility, calculates the fee preview, and creates the payout to their verified debit card. The fee is deducted from the platform's Stripe account balance unless explicitly routed to the connected account.

```typescript
// workers/instant-payout.ts
import Stripe from "stripe";

interface InstantPayoutRequest {
  connectedAccountId: string;
  amountCents: number;
  destinationCardId: string; // card_xxx from external_accounts
}

interface InstantPayoutResult {
  payoutId: string;
  feeCents: number;
  arrivalTimestamp: number; // Unix seconds
  estimatedArrivalISO: string;
  status: string;
}

function calcInstantFee(amountCents: number): number {
  return Math.min(
    Math.max(Math.round(amountCents * 0.01), 50),
    1500
  );
}

export async function createInstantPayout(
  stripe: Stripe,
  req: InstantPayoutRequest
): Promise<InstantPayoutResult> {
  const feeCents = calcInstantFee(req.amountCents);

  const payout = await stripe.payouts.create(
    {
      amount: req.amountCents,
      currency: "usd",
      method: "instant",
      destination: req.destinationCardId,
      metadata: {
        instant_fee_cents: String(feeCents),
        initiated_at: new Date().toISOString(),
      },
    },
    { stripeAccount: req.connectedAccountId }
  );

  return {
    payoutId: payout.id,
    feeCents,
    arrivalTimestamp: payout.arrival_date,
    estimatedArrivalISO: new Date(payout.arrival_date * 1000).toISOString(),
    status: payout.status,
  };
}
```

## Handling Payout Webhooks in D1

Payouts move through `paid`, `failed`, and `canceled` states asynchronously. Always listen for `payout.failed` — funds return to the Stripe balance (may take 1–2 business days). Standard payouts also fail if the bank account is closed or has incorrect routing details.

```typescript
// workers/payout-webhook-handler.ts
import Stripe from "stripe";

const PAYOUT_UPSERT_SQL = `
  INSERT INTO payouts (stripe_payout_id, connected_account_id, status,
    amount_cents, fee_cents, method, arrival_date, failure_code, updated_at)
  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
  ON CONFLICT (stripe_payout_id) DO UPDATE SET
    status = excluded.status,
    failure_code = excluded.failure_code,
    updated_at = excluded.updated_at
`;

export async function handlePayoutWebhook(
  event: Stripe.Event,
  db: D1Database
): Promise<Response> {
  const payout = event.data.object as Stripe.Payout;
  const connectedAccountId = (event as any).account ?? null;
  const now = new Date().toISOString();

  // Idempotency: events can be replayed
  const existing = await db
    .prepare(
      `SELECT status FROM payouts WHERE stripe_payout_id = ? AND status = 'paid'`
    )
    .bind(payout.id)
    .first<{ status: string }>();
  if (existing && event.type === "payout.paid") {
    return new Response("already processed", { status: 200 });
  }

  const feeCents = payout.metadata?.instant_fee_cents
    ? Number(payout.metadata.instant_fee_cents)
    : null;

  await db
    .prepare(PAYOUT_UPSERT_SQL)
    .bind(
      payout.id,
      connectedAccountId,
      payout.status,
      payout.amount,
      feeCents,
      payout.method,
      payout.arrival_date,
      payout.failure_code ?? null,
      now
    )
    .run();

  if (event.type === "payout.failed") {
    // Queue notification to seller: prompt bank details update
    // Funds automatically return to Stripe balance within 1-2 business days
    await notifyPayoutFailed(connectedAccountId, payout);
  }

  return new Response("ok", { status: 200 });
}

async function notifyPayoutFailed(
  accountId: string | null,
  payout: Stripe.Payout
): Promise<void> {
  // Implementation: send email/SMS to seller with failure reason
  console.log(
    `Payout ${payout.id} failed for ${accountId}: ${payout.failure_message}`
  );
}
```

## Anti-patterns

- **Initiating instant payouts without checking `available_payout_methods`**: The debit card must explicitly list `"instant"` in this array. A regular bank account only has `["standard"]`. Attempting an instant payout to a non-instant destination returns a `400` error.
- **Hardcoding `delay_days = 2`**: New accounts start at 7 days; always read `account.settings.payouts.schedule.delay_days` from the live account object.
- **Ignoring `debit_negative_balances`**: With `false`, Stripe pauses payouts rather than debiting the bank when the Stripe balance goes negative due to refunds or chargebacks. Track negative balance exposure at the platform level.
- **Creating payouts manually when automatic schedule is active**: Manual payouts compete with the automatic sweep. Switch the schedule to `manual` if you want full control, or rely entirely on automatic scheduling.
- **Failing to surface fee previews before confirmation**: Sellers will dispute platform fees they did not see before triggering an instant payout. Always show the 1% fee and net amount in the confirmation UI.
- **Using `arrival_date` as milliseconds**: It is Unix seconds; pass `arrival_date * 1000` to `new Date()`.

## Gotchas

- Instant payouts are US-only for debit cards. The UK has "Fast Payouts" via Faster Payments — a distinct product with separate eligibility rules.
- The 1% instant payout fee is charged against the **platform's** Stripe account balance by default, not the connected account, unless you explicitly route it otherwise.
- In test mode, instant payouts always succeed synchronously — `status` comes back as `"paid"` immediately without a webhook round-trip.
- `payout.reconciliation_status` (Stripe 2024+) indicates whether the payout has cleared the bank and appears on Stripe's reconciliation output — useful for treasury workflows.
- Payouts cannot target a currency that does not match the connected account's default currency unless multi-currency payouts are enabled for that account.
- Stripe can pause payouts on an account flagged for review without notice; check `account.payouts_enabled` before showing the "Get Paid Now" button.

## Verification

```bash
# Check payout schedule on a connected account
stripe accounts retrieve acct_xxx --expand settings.payouts.schedule

# List external accounts to verify instant eligibility
stripe external_accounts list --account=acct_xxx

# Create a test instant payout (test mode only)
stripe payouts create \
  --amount=10000 \
  --currency=usd \
  --method=instant \
  --destination=card_xxx \
  --stripe-account=acct_xxx

# Trigger payout.failed webhook event in test mode
stripe trigger payout.failed
```

```typescript
// Unit-test fee calculation edge cases
function calcInstantFee(cents: number) {
  return Math.min(Math.max(Math.round(cents * 0.01), 50), 1500);
}
console.assert(calcInstantFee(100) === 50, "minimum: $0.50 at $1.00 payout");
console.assert(calcInstantFee(5000) === 50, "still minimum at $50 payout");
console.assert(calcInstantFee(10000) === 100, "1% of $100 = $1.00");
console.assert(calcInstantFee(150001) === 1500, "capped at $15.00");
console.assert(calcInstantFee(500000) === 1500, "still capped at $5k payout");
```

## Related

- `stripe-connect-payouts.md` — general Connect payout configuration
- `stripe-connect-express.md` — express account setup and capabilities
- `stripe-connect-platform.md` — platform-level balance management
- `payout-run-scheduling-engineering.md` — internal payout run orchestration
- `stripe-cash-balance-reconciliation.md` — reconciling Stripe balance with payouts

## Sources

- https://stripe.com/docs/payouts/instant-payouts
- https://stripe.com/docs/api/payouts/create
- https://stripe.com/docs/connect/manage-payout-schedule
- https://stripe.com/docs/api/accounts/update#update_account-settings-payouts-schedule
- https://stripe.com/docs/connect/account-capabilities
