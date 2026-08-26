# Tap to Pay — NFC Mobile Point-of-Sale Integration

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your mobile application serves field service workers, pop-up shops, or
delivery drivers who need to accept card payments in person. You
currently rely on external Bluetooth card readers that cost $300+ per
unit, require charging, and frequently disconnect. You want to accept
contactless payments directly on a smartphone or tablet without
additional hardware — turning every device into a payment terminal.

## Context

Tap to Pay (also called SoftPOS or mobile POS) enables smartphones and
tablets to accept contactless payments via NFC (Near Field
Communication) without dedicated hardware. Apple launched Tap to Pay on
iPhone in 2022, and Android has supported NFC payment acceptance since
2023. In 2026, Tap to Pay is available through Stripe Terminal, Square,
Adyen, and SumUp in 30+ countries. The technology uses the device's
built-in NFC antenna to communicate with contactless cards and digital
wallets (Apple Pay, Google Pay, Samsung Pay). Payment data is encrypted
and tokenized by the payment processor's SDK — the merchant application
never handles raw card data, keeping PCI scope minimal (SAQ B-IP or
SAQ C equivalent). Transaction speed is 0.5-2 seconds, significantly
faster than chip-and-PIN.

## How NFC payment works

```
Contactless Payment Flow:

1. Merchant app creates a PaymentIntent (amount, currency)
2. App displays "Ready to accept payment" UI
3. Customer taps card/phone on merchant's device
4. NFC antenna reads encrypted card data
5. SDK sends encrypted data to payment processor
6. Processor routes to card network → issuing bank
7. Authorization response returned (approve/decline)
8. App displays result, prints/emails receipt

             ┌──────────┐
             │ Customer │
             │ Card/    │
             │ Wallet   │
             └────┬─────┘
                  │ NFC tap
             ┌────▼─────┐
             │ Merchant │
             │ Device   │
             │ (phone)  │
             └────┬─────┘
                  │ Encrypted
             ┌────▼─────┐      ┌──────────┐
             │ Payment  │─────►│ Card     │
             │ Processor│      │ Network  │
             │ (Stripe) │◄─────│ + Issuer │
             └────┬─────┘      └──────────┘
                  │ Auth result
             ┌────▼─────┐
             │ Merchant │
             │ App      │
             └──────────┘
```

## Supported payment methods

```
Contactless cards:
  → Visa payWave
  → Mastercard Contactless
  → American Express Contactless
  → Discover Contactless
  → Regional: Interac (Canada), eftpos (Australia),
    Cartes Bancaires (France), girocard (Germany)

Digital wallets:
  → Apple Pay
  → Google Pay
  → Samsung Pay
  → Garmin Pay, Fitbit Pay (wearables)

Device requirements:
  iPhone:  XS or later, iOS 16.4+
  Android: NFC-enabled, Android 9+ (varies by processor)
```

## Stripe Terminal Tap to Pay integration

```javascript
// iOS (Swift) — Stripe Terminal SDK
import StripeTerminal

class PaymentManager {
  func initializeTerminal() {
    Terminal.setTokenProvider(APIClient.shared)

    let config = LocalMobileDiscoveryConfiguration()
    Terminal.shared.discoverReaders(config, delegate: self) { error in
      if let error = error { print("Discovery failed: \(error)") }
    }
  }

  func acceptPayment(amount: Int, currency: String) {
    let params = PaymentIntentParameters(
      amount: UInt(amount),
      currency: currency,
      paymentMethodTypes: ["card_present"]
    )

    Terminal.shared.createPaymentIntent(params) { intent, error in
      guard let intent = intent else { return }

      Terminal.shared.collectPaymentMethod(intent) { intent, error in
        guard let intent = intent else { return }

        Terminal.shared.confirmPaymentIntent(intent) { intent, error in
          if let intent = intent, intent.status == .succeeded {
            // Payment successful — show receipt
          }
        }
      }
    }
  }
}

// ConnectionToken provider (backend)
class APIClient: ConnectionTokenProvider {
  func fetchConnectionToken(
    _ completion: @escaping ConnectionTokenCompletionBlock
  ) {
    // POST to your backend → Stripe API
    // Backend: stripe.terminal.connectionTokens.create()
    let token = fetchFromBackend()
    completion(token, nil)
  }
}
```

```kotlin
// Android — Stripe Terminal SDK
class PaymentActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        if (!Terminal.isInitialized()) {
            Terminal.initTerminal(
                applicationContext,
                LogLevel.VERBOSE,
                TokenProvider(),
                TerminalListener()
            )
        }

        val config = DiscoveryConfiguration.TapToPayDiscoveryConfiguration()
        Terminal.getInstance().discoverReaders(config, discoveryListener)
    }

    fun collectPayment(amount: Long) {
        val params = PaymentIntentParameters.Builder()
            .setAmount(amount)
            .setCurrency("usd")
            .build()

        Terminal.getInstance().createPaymentIntent(params, createCallback)
        // → collectPaymentMethod → confirmPaymentIntent → done
    }
}
```

## Backend integration

```javascript
// Node.js backend — connection tokens and payment management
const stripe = require('stripe')('sk_live_...');

// Endpoint: create connection token for Terminal SDK
app.post('/terminal/connection-token', async (req, res) => {
  const token = await stripe.terminal.connectionTokens.create();
  res.json({ secret: <redacted-secret> });
});

// Endpoint: capture payment (if using manual capture)
app.post('/terminal/capture/:paymentIntentId', async (req, res) => {
  const intent = await stripe.paymentIntents.capture(
    req.params.paymentIntentId
  );
  res.json({ status: intent.status });
});

// Webhook: handle terminal payment events
app.post('/webhooks/stripe', async (req, res) => {
  const event = stripe.webhooks.constructEvent(
    req.body, req.headers['stripe-signature'], webhookSecret
  );

  switch (event.type) {
    case 'payment_intent.succeeded':
      await recordSale(event.data.object);
      break;
    case 'payment_intent.payment_failed':
      await handleFailedPayment(event.data.object);
      break;
  }

  res.sendStatus(200);
});
```

## Offline and connectivity handling

```
Connectivity scenarios:
  Full online:     Normal flow, real-time authorization
  Intermittent:    Queue transactions, process when connected
  Offline mode:    Store-and-forward (limited, higher risk)

Store-and-forward:
  → Accept payment offline (limited amount, e.g., <$50)
  → Encrypt and store transaction locally
  → Forward to processor when connectivity returns
  → Risk: card may be declined on later processing
  → Not all processors support this mode

Best practices:
  □ Show connectivity status indicator in payment UI
  □ Retry failed transactions with exponential backoff
  □ Queue management: process oldest transactions first
  □ Alert merchant when offline queue reaches threshold
  □ Never store raw card data locally (use SDK encryption)
```

## Anti-patterns

- **Reading NFC data directly** — attempting to read card data
  via the device's NFC APIs instead of the payment processor's
  SDK. This makes your application in scope for PCI DSS (full SAQ
  D) and is technically infeasible on iOS. Always use the
  processor's Terminal SDK.
- **Skipping device compatibility checks** — not verifying NFC
  capability and OS version before enabling Tap to Pay. Older
  devices or outdated OS versions will fail at payment time. Check
  compatibility at app startup and show clear messaging.
- **Hardcoded amounts in local currency** — not supporting multi-
  currency for international merchants. Pass the currency from
  your backend, not hardcoded in the mobile app.
- **No receipt mechanism** — completing payment without offering
  a receipt. Many jurisdictions require receipts for in-person
  transactions. Implement email, SMS, or on-screen receipt
  delivery.

## Gotchas

- **Apple entitlement required** — Tap to Pay on iPhone requires
  an Apple entitlement that must be requested through your payment
  processor (Stripe, Adyen, etc.). You cannot use NFC for payment
  acceptance without this entitlement. Processing time: 1-2 weeks.
- **Background NFC limitations** — NFC payment acceptance only
  works when the app is in the foreground. If the app is
  backgrounded during a transaction, the NFC session terminates.
  Design the payment flow to keep the app active.
- **Regional availability** — Tap to Pay is not available in all
  countries. Availability depends on both the device platform
  (Apple/Android) and the payment processor's regional support.
  Check availability per market before launching.
- **Refunds on Tap to Pay** — refunds for Tap to Pay transactions
  are processed as card-not-present refunds (online), not as
  in-person reversals. The customer does not need to tap again.
  Ensure your refund flow handles this correctly.

## Verification

- Tap to Pay accepts contactless cards and digital wallets.
- Payment flow completes in under 5 seconds.
- Device compatibility is checked before enabling NFC acceptance.
- Backend connection token endpoint is secured and scoped.
- Receipts are delivered via email, SMS, or on-screen display.
- Offline scenarios are handled gracefully with queuing.
- PCI scope is limited to SAQ B-IP or equivalent.

## Related

- `documentation/docs/policies/payments/stripe-payment-intents.md`
- `documentation/docs/policies/payments/tokenization-vault-patterns.md`
- `documentation/docs/policies/payments/pci-dss-scope-reduction.md`

## Source URLs (verified 2026-08-16)

- Stripe Tap to Pay Documentation — https://docs.stripe.com/terminal/payments/setup-reader/tap-to-pay
- Stripe Tap to Pay on iPhone — https://stripe.com/terminal/tap-to-pay-on-iphone
- Stripe Tap to Pay on Android — https://stripe.com/newsroom/news/tap-to-pay-android
- Contactless POS: 2026 Guide to Tap Payments — https://www.getvms.com/contactless-point-of-sale-a-guide-to-contactless-payments-in-2026/
