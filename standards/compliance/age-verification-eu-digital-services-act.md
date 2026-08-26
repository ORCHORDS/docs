# Age Verification under the EU Digital Services Act — DSA Article 28 Engineering

**Project:** example project (example.com) — 21+ anonymous social platform
**Author:** example.com
**Scope:** EU users, DSA obligations, Cloudflare Workers KYC gate, anonymous attestation
**Last reviewed:** 2025-08

---

## 1. Regulatory Context

The EU Digital Services Act (Regulation (EU) 2022/2065), applicable from 17 February 2024,
imposes specific obligations on online platforms regarding the protection of minors. For example project,
the key provision is **Article 28**, which applies to any platform that is accessible to minors
and which presents a systemic risk to their safety.

### 1.1 Article 28 Obligations

Article 28 DSA requires that platforms which are accessible by minors:

1. Apply **appropriate and proportionate measures** to ensure a high level of privacy, safety, and
   security for minors on their service.
2. Assess whether their service is likely to be accessed by minors.
3. Not process personal data of minors for commercial profiling purposes.
4. Provide appropriate protection for minors' safety including content filtering and age-appropriate
   design.

**Critical note for example project:** The platform's explicit 21+ policy is itself a legal design choice.
If the platform successfully enforces the 21+ age gate at the technical layer, it may argue it is
not "accessible to minors" and thus falls outside the Article 28 scope. However, this argument
requires the age verification mechanism to be **robust** — not merely a self-declaration checkbox.

### 1.2 DSA Very Large Online Platform (VLOP) Threshold

Platforms with ≥ 45 million average monthly active users in the EU are designated as VLOPs by the
European Commission and face additional obligations (Articles 33–43). For platforms below this
threshold, Article 28 still applies via national Digital Services Coordinators.

### 1.3 Interaction with Other Frameworks

| Framework           | Relevance for example project                                         |
|---------------------|----------------------------------------------------------------|
| GDPR Art. 8         | Consent by children under 16 (member-state variable 13–16)    |
| ePrivacy Directive  | Cookie consent for minors                                      |
| AVMSD 2018/1808     | Video-sharing platforms: parental controls                     |
| Ofcom OSA (UK)      | Equivalent UK duty for user-to-user content platforms          |
| COPPA (US)          | Children under 13; irrelevant if age gate is enforced          |
| example project ToS        | Self-imposed 21+ rule — exceeds minimum regulatory threshold   |

---

## 2. Age Verification Architecture on Cloudflare Workers

example project operates a hard 21+ gate. The verification must occur before any content is served and
must not leak personal data to third parties unnecessarily.

### 2.1 Architecture Overview

```
Mobile App / Browser
        │
        ▼
Cloudflare Worker (age-gate.ts)
  ├── Check KV: has user passed verification?
  │     ├── YES → forward request to origin
  │     └── NO  → return 302 to /verify
        │
        ▼
/verify route (KYC Worker)
  ├── Option A: Third-party age attestation token (anonymous)
  ├── Option B: Credit card presence check (soft signal)
  └── Option C: ID document scan (high assurance, not required for 21+)
        │
        ▼
KV: store age_verified:{sessionId} = { verifiedAt, method, countryCode, expiresAt }
```

### 2.2 Edge Enforcement Worker

```typescript
// workers/age-gate.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Exempt paths: verification flow itself, static assets, health checks
    const url = new URL(request.url);
    const EXEMPT_PATHS = ['/verify', '/verify/', '/_assets/', '/health'];
    if (EXEMPT_PATHS.some(p => url.pathname.startsWith(p))) {
      return fetch(request);
    }

    const sessionId = getSessionId(request);
    if (!sessionId) return redirectToVerify(request, env, 'no-session');

    const record = await env.AGE_GATE_KV.get(`age_verified:${sessionId}`, 'json') as AgeRecord | null;

    if (!record) return redirectToVerify(request, env, 'not-verified');
    if (new Date(record.expiresAt) < new Date()) return redirectToVerify(request, env, 'expired');

    // Attach verification metadata for downstream use
    const req2 = new Request(request);
    req2.headers.set('X-Age-Verified', '1');
    req2.headers.set('X-Age-Method', record.method);
    return fetch(req2);
  },
};

interface AgeRecord {
  verifiedAt: string;
  method:     'attestation' | 'card-check' | 'id-scan';
  countryCode: string;
  expiresAt:  string;
}

function getSessionId(req: Request): string | null {
  const cookie = req.headers.get('cookie') ?? '';
  const m = cookie.match(/wam_sid=([^;]+)/);
  return m ? m[1] : null;
}

function redirectToVerify(req: Request, env: Env, reason: string): Response {
  const url = new URL(req.url);
  const dest = new URL('https://example.com/verify');
  dest.searchParams.set('return', url.pathname);
  dest.searchParams.set('reason', reason);
  return Response.redirect(dest.toString(), 302);
}
```

---

## 3. KYC Gate and Verification Methods

### 3.1 Method A — Anonymous Age Attestation Token

Several privacy-preserving age attestation services issue a cryptographically signed token that
asserts only "user is 18+" (or 21+) without transmitting any identity data to the relying party.
These include:

- **AgeID** (Yoti) — issues a W3C Verifiable Credential asserting age threshold
- **Apple Age Token** — iOS 17+ can issue a non-linkable age token via Sign in with Apple
- **Privacy Pass** (IETF RFC 9576) — issuer signs a token; verifier cannot link to issuer record

For example project, the recommended flow is:

1. User visits `/verify` on the mobile app.
2. App requests an age attestation token from the chosen attestation provider.
3. Token is sent to the verification Worker.
4. Worker verifies the token signature against the provider's public key (fetched from a well-known
   endpoint and cached in KV).
5. On valid token: write `age_verified:{sessionId}` to KV; issue a signed session upgrade cookie.

```typescript
async function verifyAttestationToken(
  token: string,
  env: Env
): Promise<{ valid: boolean; method: string }> {
  // Fetch provider public key (cached 1h in KV)
  const pubKeyRaw = await env.AGE_GATE_KV.get('pubkey:ageid') ??
    await fetchAndCacheProviderKey(env);

  const cryptoKey = await importPublicKey(pubKeyRaw);
  const [header, payload, sig] = token.split('.');
  const data = new TextEncoder().encode(`${header}.${payload}`);
  const sigBytes = base64urlDecode(sig);

  const valid = await crypto.subtle.verify(
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    cryptoKey,
    sigBytes,
    data,
  );

  if (!valid) return { valid: false, method: '' };

  const claims = JSON.parse(atob(payload));
  // claims.age_over_21 must be true
  return { valid: claims.age_over_21 === true, method: 'attestation' };
}
```

### 3.2 Method B — Credit/Debit Card Presence (Soft Signal)

A card lookup (BIN check, not a charge) provides weak age assurance: card holders are generally 18+.
This is acceptable as a secondary signal for lower-risk content but insufficient as a sole mechanism
under DSA Article 28 for a 21+ platform.

### 3.3 Method C — Document Scan (High Assurance)

For jurisdictions demanding high-assurance age verification (e.g., UK OSA, German JuSchG), an ID
document scan via a third-party KYC provider (Onfido, Veriff, Jumio) is required. The KYC Worker
calls the provider API and receives a DOB or age-threshold pass/fail.

**Privacy minimisation:** request only the age threshold result, not the full document data.
Do not store any document images in R2 or D1 — store only the verification outcome and provider
reference ID.

---

## 4. Anonymous Architecture — Minimising Re-identification Risk

example project is an anonymous platform. Age verification creates a tension: confirming age typically
requires some identity signal. Mitigations:

### 4.1 Unlinkability

After successful age verification, the platform must store proof of verification but **not** link
the real identity to the pseudonymous user account.

Architecture:
- Age verification session (`verify_sid`) is a separate, short-lived identifier.
- Once verified, a new `wam_sid` session is issued that is not computationally derivable from
  `verify_sid`.
- The KYC provider reference ID is stored in a separate D1 table, not in the main user table.

### 4.2 Data Minimisation per GDPR Article 5(1)(c)

- Do not retain the document scan beyond the verification event.
- KV record: store only `{ verifiedAt, method, countryCode, expiresAt }`.
- D1 audit row: store only `{ hashed_verify_sid, method, country, passed, timestamp }`.

### 4.3 Retention

Age verification proof should be retained for as long as the account is active plus any applicable
legal hold period. KV TTL should match session expiry. D1 audit rows are retained per the platform
data retention policy.

---

## 5. Mobile Friction Reduction

Age verification on mobile must be low-friction enough that legitimate adult users complete it,
while remaining robust enough to deter minors.

### 5.1 Native Biometric Link

On iOS 17+, Sign in with Apple can return an age-over-threshold claim. Trigger this during the
onboarding flow using `ASAuthorizationController` with the `ageThresholdAbove` scope.

On Android, Google Identity Services does not yet support age attestation directly; use the
attestation provider SDK instead.

### 5.2 Progressive Friction

```
Step 1: Self-declaration checkbox ("I confirm I am 21 or over")
         → sufficient for first session, low trust
Step 2: After 3 sessions, prompt for attestation token
         → medium trust, anonymous
Step 3: On any payment action, require attestation token or card check
         → higher trust signal
```

This graduated approach reduces drop-off while fulfilling the "appropriate and proportionate"
language of DSA Article 28.

### 5.3 Re-verification Triggers

Re-verify the user if:
- The session expires (KV TTL elapsed).
- The user changes device or clears app data.
- Behavioural signals (ML anomaly) suggest a potentially minor user.

---

## 6. Enforcement Evidence and DSA Reporting

Under DSA Article 42, Very Large Online Platforms must publish annual Transparency Reports.
Even non-VLOP platforms should maintain internal evidence of their age assurance measures
for national DSC inquiries.

Evidence to retain:
1. **Architecture diagram** of the age gate system.
2. **Verification rate metrics**: % of new registrations that complete each method.
3. **Failure logs**: anonymised, aggregated counts of gate refusals by country.
4. **Provider contracts**: SLA and data-processing agreements with KYC providers.
5. **DPIA** (GDPR Article 35): age verification involves biometric/identity data.

---

## 7. Checklist

- [ ] DSA Article 28 applicability assessment documented
- [ ] Age gate Worker deployed as first Worker in request chain
- [ ] KV store: `age_verified:{sessionId}` records with expiry
- [ ] At least one anonymous attestation method implemented (Yoti/Apple/Privacy Pass)
- [ ] Unlinkable session architecture: verify_sid ≠ wam_sid
- [ ] DPIA completed for age verification processing
- [ ] KYC provider DPA (GDPR Art. 28) signed
- [ ] Mobile: native attestation API integrated (iOS 17+ Sign in with Apple age claim)
- [ ] Progressive friction ladder implemented
- [ ] Audit log in D1 (hashed, no raw identity data)
- [ ] Re-verification triggers configured

---

## 8. References

- EU Digital Services Act (EU) 2022/2065, Articles 28, 33–43
- GDPR Articles 5, 8, 25, 35
- UK Online Safety Act 2023, Sections 34–41
- German Jugendschutzgesetz (JuSchG) 2021 amendments
- IETF RFC 9576 — Privacy Pass Architecture
- W3C Verifiable Credentials Data Model 2.0
- Apple Developer Documentation — Sign in with Apple (Age Tokens)
- EDPB Guidelines on Data Minimisation (Art. 5(1)(c))
