# age-gating

**Issue:** Age verification — design, implementation, gotchas
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your platform is 18+ (or 21+). You add a "Are you 18+?" self-
attest screen. A 14-year-old clicks "Yes, I am 18." They're in.
You have no age verification. Apple/Google regulators notice.
Fines. App store rejection.

## Root cause
Self-attest age gates are a **legal fiction**, not a control.
They exist to satisfy the "minimum steps" requirement of app
store guidelines, not to actually verify age. To verify age,
you need a third-party age estimation or ID verification
service.

**Source:** Apple App Store Guidelines 1.4.3:
https://developer.apple.com/app-store/review/guidelines/

> "Apps that feature user-generated content ... must include ...
> a method for filtering objectionable material, an easy-to-find
> mechanism for users to flag objectionable content, and a way
> to take action against users who post objectionable content."

> "Apps that require users to provide personal information to
> function ... must include a privacy policy."

For 18+ content, the guidelines reference various jurisdictional
age-verification standards (UK Age-Appropriate Design Code,
EU DSA, US state laws).

## Fix
A layered age gate (each layer adds friction but more accuracy):

### Layer 1: Self-attest (low friction, low accuracy)
```ts
// First-time visit
const agreed = localStorage.getItem('age-attested') === 'true';
if (!agreed) {
  return <AgeGate onConfirm={() => {
    localStorage.setItem('age-attested', 'true');
    localStorage.setItem('age-attested-at', Date.now().toString());
  }} />;
}
```

This satisfies "user took an affirmative step." For some
jurisdictions, this is sufficient.

### Layer 2: Account age + behavior (medium friction, medium accuracy)
- Require a verified email (1-2 days of account age)
- Cross-check against a social-login ID (most major providers
  return age range or birthday for some providers)
- Track user behavior and re-prompt on suspicious signals

### Layer 3: ID verification (high friction, high accuracy)
For high-stakes regions (UK, some US states, EU) or premium
content access, use a third-party ID verification service:
- **Onfido** — government ID + selfie
- **Jumio** — government ID + liveness
- **Yoti** — government ID + biometric
- **Persona** — flexible verification
- **Stripe Identity** — if you already use Stripe

```ts
// On onboarding high-stakes feature
const verification = await verifyId(userId, env);
if (!verification.verified || verification.age < 18) {
  return new Response('Age verification required', { status: 403 });
}
```

### Layer 4: Continuous monitoring
- Re-prompt on suspicious signals (account takeover, new device,
  region change)
- Cross-reference against age-estimation ML (e.g. Yoti Age
  Estimation, which estimates age from a selfie)

## What NOT to do

- **Don't store the ID document** beyond the verification window.
  Store the verification result (yes/no) + timestamp, not the
  document. Less PII = less liability.
- **Don't share verification results with third parties** without
  consent. The verification is the user's data.
- **Don't bypass the gate in dev/test** without a clearly labeled
  dev-mode flag. The accidental "I forgot to re-enable" bug is
  a real compliance failure.

## Verification
- **Test:** `test/age-gate.test.ts > 14-year-old cannot bypass
  self-attest` — passes (but acknowledges the gate is low-strength)
- **Live:** Audit log records every age-gate confirmation with
  timestamp + IP + user-agent
- **Pen test:** Annual third-party review of age-verification flow

## Gotchas
- **Self-attest age gates are not a control.** They are a
  legal step. Document this in your T&S policy.
- **The user's age may change.** A user who registered at 17 is
  now 18 (or 21). Re-prompt on the birthday boundary.
- **Age estimation ML is not 100% accurate.** It returns a
  probability range. For 18+ content, require 95% confidence
  that the user is 18+ (not 50% confidence).
- **Different jurisdictions require different age gates.**
  UK requires "age-appropriate design" for users under 18;
  EU DSA requires specific notices for minors; US COPPA
  requires parental consent for under-13.
- **If you process minors' data at all**, GDPR-K applies (UK
  Age-Appropriate Design Code) with very strict rules.

## Related
- `compliance/region-matrix.md` (where age gates apply)
- `compliance/gdpr-article-17-erasure.md` (data minimization)
- Apple guidelines: https://developer.apple.com/app-store/review/guidelines/
- UK Age-Appropriate Design Code: https://ico.org.uk/for-organisations/guide-to-data-protection/ico-codes-of-practice-for-age-appropriate-design/
