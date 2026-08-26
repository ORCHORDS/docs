# PSD2 Strong Customer Authentication via Cloudflare Workers

**Project:** example project (example.com) — 21+ anonymous social platform
**Author:** example.com
**Scope:** EU/UK users, PSD2/SCA requirements, 3DS2, Cloudflare Workers proxy, mobile biometrics
**Last reviewed:** 2025-08

---

## 1. Regulatory Context

The EU Payment Services Directive 2 (PSD2, Directive 2015/2366/EU) and the associated EBA
Regulatory Technical Standards on Strong Customer Authentication (EBA RTS on SCA) require that
payment service providers apply SCA whenever a payer:

1. Accesses their payment account online.
2. Initiates an electronic payment transaction.
3. Carries out any action through a remote channel which may imply a risk of payment fraud.

The SCA requirement took full effect from 31 December 2020 (retail e-commerce) in the EU, and
14 March 2022 for UK firms (UK FCA mandate).

**Scope for example project:** The platform's monetisation features — premium subscriptions, in-app
purchases, tipping, and creator payouts — involve card-not-present transactions. Any checkout
flow must apply SCA unless an applicable exemption is invoked.

---

## 2. SCA Requirements

### 2.1 Authentication Factors

SCA requires authentication using **at least two** of the following three independent factors:

| Factor category   | Examples                                        |
|-------------------|-------------------------------------------------|
| **Knowledge**     | Password, PIN, security question answer         |
| **Possession**    | Mobile device (OTP), hardware token, SIM card   |
| **Inherence**     | Fingerprint, Face ID, voice recognition         |

The factors must be independent: compromise of one must not undermine the reliability of the others.
A fingerprint on a mobile device where the device itself is the possession factor requires careful
segregation to satisfy the independence requirement.

### 2.2 Dynamic Linking (RTS Article 5)

For payment transactions, SCA must include a dynamic linking element that binds the
authentication to:
- The **specific transaction amount**.
- The **specific payee**.

If either changes after SCA is applied, SCA must be re-run. This prevents an attacker from
manipulating the amount or payee between authentication and execution.

### 2.3 Authentication Code Requirements

The authentication code generated must be:
- Unique to each transaction.
- Resistant to brute-force attack.
- Expire within a reasonable time window (typically 5–10 minutes).
- Invalidated upon use.

---

## 3. SCA Exemptions (RTS Articles 10–18)

The following categories of transactions are exempt from SCA, subject to risk-based conditions:

| Exemption                        | Conditions                                                      |
|----------------------------------|-----------------------------------------------------------------|
| Low-value transactions           | ≤ €30; cumulative limit ≤ €100 or 5 consecutive transactions    |
| Recurring transactions           | Same amount, same payee; SCA on first transaction only          |
| Trusted beneficiaries            | Payee whitelisted by payer; SCA to add to whitelist             |
| Corporate payment processes      | B2B with dedicated payment processes and legal entities         |
| Transaction risk analysis (TRA)  | Fraud rate below EBA threshold; amount ≤ €500                   |
| Contactless at POS               | ≤ €50 per transaction; cumulative ≤ €150 or 5 transactions      |
| Account information access       | ≤ 90 days since last SCA for account info only                  |

For example project the most relevant exemptions are:
- **Low-value**: small tip transactions under €30.
- **Recurring**: monthly subscription renewals after first SCA-authenticated payment.
- **TRA**: if the platform's fraud rate stays below the EBA threshold.

### 3.1 TRA Fraud Rate Thresholds (RTS Article 18)

| Transaction value    | Maximum fraud rate (of total transaction value) |
|----------------------|-------------------------------------------------|
| Up to €100           | 0.13%                                           |
| €100 – €250          | 0.06%                                           |
| €250 – €500          | 0.01%                                           |
| Above €500           | TRA exemption not available                     |

The platform must monitor and report its actual fraud rate to its Payment Service Provider (PSP)
to claim TRA exemptions. If the rate is exceeded, the PSP must immediately re-apply SCA.

---

## 4. 3D Secure 2 (3DS2) via Cloudflare Workers Proxy

### 4.1 Why Proxy Through a Worker

Implementing 3DS2 directly requires hosting a PCI-DSS-scoped back-end. Proxying the 3DS2
redirect flow through a Worker provides:
- Edge-level routing without exposing origin server.
- Injecting the `X-Forwarded-For` chain correctly for PSP fraud signals.
- Storing the 3DS2 authentication result in KV for later verification.
- Logging the outcome for SCA evidence records.

### 4.2 3DS2 Flow via Worker

```
Browser/App → Worker (checkout.ts)
  │
  ├── POST /checkout/initiate
  │     Worker calls PSP API to create PaymentIntent
  │     PSP returns { clientSecret, authenticationUrl, threeDSMethod }
  │
  ├── Worker returns { clientSecret } to client
  │
  ├── Client loads 3DS2 iframe / redirect using clientSecret
  │     (handled by PSP JS SDK or native 3DS2 SDK on mobile)
  │
  ├── PSP redirects to Worker callback: POST /checkout/callback
  │     Worker receives { paRes, transactionId, eci, authenticationValue }
  │     Verifies ECI indicates successful authentication (ECI 05/02)
  │     Stores result in KV: sca:{transactionId} = { eci, authValue, expiresAt }
  │
  └── Worker finalises payment: POST to PSP charge endpoint with authenticationValue
```

### 4.3 Worker: Checkout Initiation

```typescript
// workers/checkout.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/checkout/initiate' && request.method === 'POST') {
      return handleInitiate(request, env);
    }
    if (url.pathname === '/checkout/callback' && request.method === 'POST') {
      return handleCallback(request, env);
    }
    return new Response('Not found', { status: 404 });
  },
};

async function handleInitiate(request: Request, env: Env): Promise<Response> {
  const { amount, currency, payeeId, userId } = await request.json() as CheckoutRequest;

  // Apply SCA exemption logic
  const exemption = await determineExemption(env, userId, amount, payeeId);

  const pspResponse = await fetch(env.PSP_API_URL + '/payment_intents', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.PSP_SECRET_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      amount,
      currency,
      payment_method_types: ['card'],
      use_stripe_sdk: true,
      metadata: { userId, payeeId, exemption },
      // Request SCA exemption if applicable
      ...(exemption ? { payment_method_options: { card: { request_three_d_secure: 'automatic' } } } : {}),
    }),
  });

  const intent = await pspResponse.json();
  return Response.json({ clientSecret: <redacted-secret> exemption });
}
```

### 4.4 Dynamic Linking in Worker

Before finalising the charge, re-verify that the amount and payee match what was authenticated:

```typescript
async function verifyDynamicLinking(
  env: Env,
  transactionId: string,
  amount: number,
  payeeId: string
): Promise<boolean> {
  const original = await env.SCA_KV.get(`sca_init:${transactionId}`, 'json') as {
    amount: number;
    payeeId: string;
  } | null;

  if (!original) return false;
  return original.amount === amount && original.payeeId === payeeId;
}
```

### 4.5 ECI Code Handling

The Electronic Commerce Indicator (ECI) code returned after 3DS2 authentication indicates the
authentication outcome:

| ECI | Meaning                              | Proceed? |
|-----|--------------------------------------|----------|
| 05  | Full authentication — cardholder authenticated | Yes |
| 06  | Authentication attempted — no guaranty | Yes (liability shifts) |
| 07  | Authentication not performed         | No SCA — apply exemption or decline |
| 02  | Full authentication (Mastercard scheme) | Yes |
| 01  | Authentication attempted (Mastercard) | Yes (liability shifts) |
| 00  | Not authenticated                    | Decline unless TRA applies |

Store ECI alongside every payment record in D1:

```sql
CREATE TABLE payment_transactions (
  id              TEXT PRIMARY KEY,
  user_id         TEXT NOT NULL,
  payee_id        TEXT NOT NULL,
  amount          INTEGER NOT NULL,     -- in pence/cents
  currency        TEXT NOT NULL,
  eci             TEXT,
  auth_value      TEXT,                 -- CAVV / authentication value
  exemption       TEXT,                 -- which exemption was applied, if any
  status          TEXT NOT NULL DEFAULT 'pending',
  psp_intent_id   TEXT,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  completed_at    TEXT
);
```

---

## 5. Exemption Decision Engine

```typescript
async function determineExemption(
  env: Env,
  userId: string,
  amount: number,  // in minor units (pence)
  payeeId: string
): Promise<string | null> {
  const amountEur = amount / 100;

  // 1. Low-value exemption
  if (amountEur <= 30) {
    const state = await getLowValueState(env, userId);
    if (state.cumulativeEur + amountEur <= 100 && state.consecutiveCount < 5) {
      await incrementLowValueState(env, userId, amountEur);
      return 'low-value';
    }
    // Reset low-value state on SCA
    await resetLowValueState(env, userId);
  }

  // 2. Recurring subscription exemption
  const isRecurring = await isKnownRecurringPair(env, userId, payeeId);
  if (isRecurring) return 'recurring';

  // 3. TRA exemption (requires fraud rate check with PSP)
  if (amountEur <= 250) {
    const fraudRate = await getActualFraudRate(env);
    if (amountEur <= 100 && fraudRate < 0.0013) return 'tra';
    if (amountEur <= 250 && fraudRate < 0.0006) return 'tra';
  }

  // No exemption available — full SCA required
  return null;
}
```

---

## 6. Mobile Biometric Authentication Integration

### 6.1 Decoupled Authentication

PSD2 RTS Article 9 permits decoupled authentication where the authentication occurs on a device
separate from the transaction initiation. For mobile:

- Transaction initiated in the mobile app (possession factor: device).
- Biometric authentication (Face ID / Touch ID) provides the inherence factor.
- Together, device possession + biometric meets the two-factor SCA requirement.

### 6.2 iOS Integration (LocalAuthentication + Secure Enclave)

```swift
// iOS: request biometric authentication as SCA factor
import LocalAuthentication

func performSCABiometric(completion: @escaping (Bool, Error?) -> Void) {
  let context = LAContext()
  context.evaluatePolicy(
    .deviceOwnerAuthenticationWithBiometrics,
    localizedReason: "Authenticate to complete payment",
    reply: { success, error in
      DispatchQueue.main.async { completion(success, error) }
    }
  )
}
```

After successful biometric authentication, the app requests a one-time token from the backend
Worker (possession factor: app-bound cryptographic key in Secure Enclave) and includes it in
the payment initiation request.

### 6.3 Android Integration (BiometricPrompt + StrongBox)

```kotlin
// Android: StrongBox-backed key provides possession factor
val keyPairGenerator = KeyPairGenerator.getInstance(
  KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore"
)
keyPairGenerator.initialize(
  KeyGenParameterSpec.Builder("wam_sca_key", KeyProperties.PURPOSE_SIGN)
    .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
    .setUserAuthenticationRequired(true)
    .setIsStrongBoxBacked(true)  // requires StrongBox TEE
    .build()
)
val keyPair = keyPairGenerator.generateKeyPair()
// Sign transaction challenge with private key; send signature to Worker for verification
```

### 6.4 Worker Verification of Mobile Biometric SCA

```typescript
async function verifyMobileSca(
  env: Env,
  userId: string,
  challenge: string,
  signature: string,
  publicKeyJwk: JsonWebKey
): Promise<boolean> {
  const pubKey = await crypto.subtle.importKey(
    'jwk', publicKeyJwk,
    { name: 'ECDSA', namedCurve: 'P-256' },
    false, ['verify']
  );
  const data = new TextEncoder().encode(challenge);
  const sigBytes = base64urlDecode(signature);
  return crypto.subtle.verify({ name: 'ECDSA', hash: 'SHA-256' }, pubKey, sigBytes, data);
}
```

Register each user's public key in D1 on enrolment:

```sql
CREATE TABLE sca_public_keys (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL,
  public_key  TEXT NOT NULL,   -- JWK format
  device_id   TEXT NOT NULL,
  enrolled_at TEXT NOT NULL DEFAULT (datetime('now')),
  last_used   TEXT,
  revoked_at  TEXT
);
```

---

## 7. SCA Evidence and Audit Trail

Under PSD2 Article 72 and EBA Guidelines on Security Measures, the PSP (and platform acting as
merchant) must retain evidence of SCA for the dispute resolution period (13 months minimum).

Log every SCA event to D1:

```sql
CREATE TABLE sca_audit (
  id                TEXT PRIMARY KEY,
  transaction_id    TEXT NOT NULL,
  user_id           TEXT NOT NULL,
  method            TEXT NOT NULL,    -- '3ds2' | 'biometric' | 'otp'
  factors_used      TEXT NOT NULL,    -- JSON: ['possession', 'inherence']
  eci               TEXT,
  exemption_applied TEXT,
  outcome           TEXT NOT NULL,    -- 'authenticated' | 'failed' | 'abandoned'
  ip_country        TEXT,
  user_agent        TEXT,
  created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
```

---

## 8. UK PSD2 / FCA SCA Requirements

Post-Brexit, UK firms comply with the FCA's SCA requirements under the Payment Services
Regulations 2017 (as amended). Requirements are substantially equivalent to the EBA RTS.
Key differences:
- UK FCA applies SCA to mail-order/telephone-order (MOTO) transactions differently.
- FCA thresholds for contactless may differ from EU thresholds.
- UK firms must use the FCA's updated fraud reporting template.

example project should apply the more conservative EU RTS thresholds when serving both EU and UK users.

---

## 9. Checklist

- [ ] PSD2 SCA required for all new card transactions above €30 (or equivalent)
- [ ] 3DS2 flow implemented via PSP SDK and Worker callback
- [ ] Dynamic linking: amount and payee verified before charge finalisation
- [ ] ECI code captured and stored in D1 `payment_transactions`
- [ ] Low-value exemption counter maintained in KV (cumulative EUR and consecutive count)
- [ ] Recurring exemption: SCA applied on first transaction; subsequent exempt
- [ ] TRA fraud rate monitored; exemption disabled if rate exceeds EBA threshold
- [ ] Mobile biometric SCA: device key registered in D1 `sca_public_keys`
- [ ] Biometric signature verified in Worker using WebCrypto ECDSA
- [ ] SCA audit log in D1 `sca_audit` with 13-month retention
- [ ] PSP contract includes SCA liability shift clauses
- [ ] UK FCA SCA requirements applied for GB users

---

## 10. References

- PSD2 Directive 2015/2366/EU, Articles 4, 72, 97–98
- EBA Regulatory Technical Standards on SCA — Commission Delegated Regulation (EU) 2018/389
- EBA Guidelines on Security Measures for Operational and Security Risks (EBA/GL/2017/17)
- EBA Opinion on the Application of SCA to Corporate Payments (2018)
- UK Payment Services Regulations 2017 (SI 2017/752), as amended 2021
- FCA Guidance on Strong Customer Authentication (PS21/19)
- EMVCo 3DS2 Specification 2.3
- W3C Web Authentication (WebAuthn) Level 3
- FIDO Alliance FIDO2 Client-to-Authenticator Protocol (CTAP2)
- Cloudflare Workers WebCrypto API — `crypto.subtle`
