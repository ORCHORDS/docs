# Subscription Dunning — Retry Strategies and Failed Payment Recovery

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your SaaS subscription business loses 20-40% of churned customers to
involuntary churn — failed payments that silently cancel subscriptions
without the customer intending to leave. Recurring charges fail due to
expired cards, insufficient funds, or issuer declines, and your system
either immediately cancels the subscription or retries at fixed intervals
with no intelligence. Customers complain they were canceled without
warning. Revenue recovery is manual (support tickets) or nonexistent.

## Context

Dunning management is the systematic process of recovering failed
subscription payments through automated retries, targeted customer
communication, and intelligent escalation. The term comes from debt
collection ("to dun" = to make persistent demands for payment). In 2026,
modern dunning systems use ML-based retry timing, decline code
classification, and multi-channel recovery (email, SMS, in-app) to
recover 47-85% of failed payments. Every major billing platform (Stripe,
Chargebee, Recurly, Braintree) offers built-in dunning, but the default
configurations are rarely optimal — tuning retry logic and communication
sequences is critical.

## Decline classification

The first step in dunning is classifying the decline type:

| Type | Meaning | Retry? | Examples |
|---|---|---|---|
| **Hard decline** | Permanent rejection | No | Stolen card, closed account, invalid number |
| **Soft decline** | Temporary failure | Yes | Insufficient funds, issuer unavailable, rate limit |
| **Fraud decline** | Suspected fraud | No | Issuer fraud block, velocity check failure |

```
Decline code → classification → action:

  Hard decline → stop retrying → notify customer → grace period
  Soft decline → smart retry → escalate if retries exhausted
  Fraud decline → stop retrying → flag for review → notify customer
```

## Retry strategies

### Fixed interval (naive)

```
Day 0: charge fails
Day 3: retry
Day 6: retry
Day 9: retry (final)
Day 10: cancel subscription

Problems:
  → Ignores decline reason
  → Misses optimal retry windows
  → Same timing for all failure types
```

### Smart retry (recommended)

```
Soft decline retry schedule:
  Attempt 1: 4-6 hours later (transient network/issuer issues)
  Attempt 2: 24 hours later (next business day)
  Attempt 3: 3 days later (after potential payday)
  Attempt 4: 7 days later (weekly pay cycle)
  Attempt 5: 14 days later (biweekly pay cycle)

Timing optimizations:
  → Retry after payday cycles (1st, 15th of month)
  → Retry during business hours (issuer approval rates higher)
  → Avoid weekends and holidays (lower approval rates)
  → Vary retry time of day across attempts
```

### ML-based retry (advanced)

```
Input signals:
  - Decline code and issuer response
  - Customer payment history (past success rates)
  - Card type (debit vs. credit)
  - Geographic pay cycles
  - Time of day and day of week
  - Issuer-specific approval patterns

Output:
  - Optimal retry timestamp
  - Probability of success
  - Whether to retry at all

Recovery rate: 70-85% (vs. 47% industry median)
```

## Dunning email sequence

```
Email 1 (Day 0): "Payment failed — we'll retry automatically"
  → Informational, no action required from customer
  → Include last-4 digits of card on file

Email 2 (Day 3): "Payment still failing — update your card"
  → One-click link to update billing info
  → Show what they'll lose (feature list)

Email 3 (Day 7): "Your subscription is at risk"
  → Urgency messaging
  → Direct link to billing portal
  → Offer to extend grace period

Email 4 (Day 14): "Last chance — subscription cancels in 3 days"
  → Final warning with clear deadline
  → One-click payment update
  → Support contact for assistance

Email 5 (Day 17): "Your subscription has been canceled"
  → Confirmation of cancellation
  → Easy reactivation link
  → Win-back offer (optional discount)

Email 6 (Day 30): "We miss you — reactivate with 20% off"
  → Win-back campaign
  → Time-limited offer
```

## Grace period design

```
Grace period: time between first failure and cancellation

Recommended: 14-28 days (varies by business)

During grace period:
  □ Service continues (do not degrade immediately)
  □ Automated retries run on schedule
  □ Dunning emails sent at intervals
  □ In-app banner: "Payment issue — update billing"
  □ Usage data preserved (no data deletion)

After grace period:
  □ Subscription moves to "past due" → "canceled"
  □ Access revoked (or downgraded to free tier)
  □ Data retained for 30-90 days (reactivation window)
```

## Implementation (Stripe example)

```javascript
// Configure Stripe subscription retry settings
const subscription = await stripe.subscriptions.create({
  customer: 'cus_123',
  items: [{ price: 'price_monthly' }],
  payment_behavior: 'default_incomplete',
  payment_settings: {
    payment_method_options: {
      card: {
        request_three_d_secure: 'automatic',
      },
    },
    save_default_payment_method: 'on_subscription',
  },
});

// Webhook handler for failed payments
app.post('/webhooks/stripe', async (req, res) => {
  const event = req.body;

  switch (event.type) {
    case 'invoice.payment_failed':
      const invoice = event.data.object;
      const attempt = invoice.attempt_count;

      if (attempt === 1) {
        await sendDunningEmail(invoice.customer, 'payment_failed_first');
      } else if (attempt >= 4) {
        await sendDunningEmail(invoice.customer, 'final_warning');
      }
      break;

    case 'customer.subscription.deleted':
      await sendDunningEmail(
        event.data.object.customer,
        'subscription_canceled'
      );
      await scheduleWinBackEmail(event.data.object.customer, 30);
      break;
  }

  res.sendStatus(200);
});
```

## Recovery metrics

| Metric | Definition | Target |
|---|---|---|
| **Recovery rate** | % of failed payments eventually collected | >70% |
| **Involuntary churn rate** | % of subscribers lost to payment failure | <2% monthly |
| **Days to recover** | Average days from first failure to recovery | <7 days |
| **Dunning email open rate** | % of dunning emails opened | >50% |
| **Card update rate** | % of customers who update payment method | >15% |

## Anti-patterns

- **Immediate cancellation on first failure** — canceling a
  subscription on the first failed charge. Most soft declines succeed
  on retry. Always implement a grace period and retry schedule before
  cancellation.
- **Retrying hard declines** — repeatedly charging a card that has
  been reported stolen or an account that has been closed wastes
  processing fees and can trigger issuer penalties. Classify decline
  codes and stop retrying hard declines.
- **Silent failure** — letting payments fail without notifying the
  customer. Customers cannot fix what they do not know about. Send
  dunning notifications through multiple channels (email, in-app,
  SMS).
- **One-size-fits-all retry timing** — using the same retry interval
  regardless of decline reason, card type, or geography. Smart retry
  timing based on payday cycles and issuer patterns significantly
  improves recovery rates.

## Gotchas

- **Payment processor fees on retries** — most processors charge a
  fee per authorization attempt, even failed ones. Excessive retries
  on hopeless charges accumulate fees. Limit total retry attempts
  (5-7 max) and stop early on hard declines.
- **Account updater vs. dunning** — card network account updaters
  (Visa Account Updater, Mastercard ABU) automatically update expired
  card details. If your processor supports account updater, many
  "expired card" failures resolve without dunning. Check if the card
  was updated before sending dunning emails.
- **SCA/3DS complications** — in regions with Strong Customer
  Authentication (EU), failed payments may require customer
  interaction (3DS challenge) that cannot be retried automatically.
  Dunning emails must link to a payment page that triggers the
  authentication flow.
- **Grace period and revenue recognition** — during the grace period,
  the customer has access but has not paid. Accounting treatment
  (ASC 606 / IFRS 15) depends on whether collection is probable.
  Consult finance on revenue recognition during grace periods.

## Verification

- Decline codes are classified into hard, soft, and fraud categories.
- Smart retry logic varies timing based on decline type and pay cycles.
- Dunning email sequence covers the full grace period with escalation.
- Grace period allows 14-28 days before cancellation.
- Recovery rate is tracked and exceeds 70%.
- Hard declines stop retrying immediately.
- Win-back campaigns target involuntarily churned customers.

## Related

- `documentation/docs/policies/payments/network-tokenization-visa-mastercard.md`
- `documentation/docs/policies/payments/stripe-webhook-integration.md`
- `documentation/docs/policies/payments/3ds-strong-customer-authentication.md`

## Source URLs (verified 2026-08-16)

- Dunning Management for SaaS 2026 — https://www.chargebee.com/blog/dunning-management-for-saas-business/
- Failed Payment Recovery Dunning Playbook 2026 — https://www.digitalapplied.com/blog/failed-payment-recovery-dunning-playbook-2026
- Subscription Payment Retry Strategy Guide 2026 — https://www.slickerhq.com/resources/blog/complete-payment-retry-strategy-subscription
- Why Subscription Payments Fail 2026 — https://baremetrics.com/blog/why-subscription-payments-fail
