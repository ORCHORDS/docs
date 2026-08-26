# Biometric Data Privacy — BIPA, GDPR, and Engineering Compliance

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your application uses facial recognition for login, fingerprint
scanning for attendance, or voice prints for customer verification.
You store biometric templates alongside user profiles in your primary
database with no specific retention policy. Your privacy policy
mentions "biometric data" but does not specify purpose, duration, or
destruction schedule. A user in Illinois files a complaint, and you
discover that BIPA (Biometric Information Privacy Act) allows private
lawsuits with statutory damages of $1,000-$5,000 per violation — and
your user base of 10,000 Illinois residents represents potential
exposure of $10-50 million.

## Context

Biometric data (fingerprints, faceprints, voiceprints, iris scans,
retinal patterns, hand geometry) is among the most sensitive personal
data because it is immutable — unlike passwords, biometric identifiers
cannot be changed if compromised. In 2026, biometric data is regulated
under multiple overlapping frameworks: Illinois BIPA (the most
aggressive, with private right of action), GDPR Article 9 (special
category data), Texas CUBI, Washington state biometric law, and over
15 US state biometric privacy laws enacted between 2023-2026. BIPA has
produced landmark settlements: Meta/Facebook ($650M for facial
recognition tagging), Google ($100M for Google Photos face grouping),
and TikTok ($92M). The safest engineering approach is to design
biometric handling to meet BIPA requirements — if you are compliant
with BIPA, you clear most other jurisdictions by default.

## Regulatory landscape

```
Illinois BIPA (most restrictive):
  → Written informed consent BEFORE collection
  → Written retention/destruction policy (publicly available)
  → No sale, lease, trade, or profit from biometric data
  → Private right of action (individuals can sue directly)
  → Damages: $1,000 negligent / $5,000 intentional per violation
  → No statute of limitations defense (per IL Supreme Court)
  → Applies to: any entity possessing biometric data of IL residents

GDPR Article 9:
  → Biometric data = special category data
  → Processing prohibited by default
  → Requires explicit consent OR other lawful basis
  → DPIA (Data Protection Impact Assessment) mandatory
  → Penalties: up to €20M or 4% global revenue

Texas CUBI:
  → Informed consent required for capture
  → Destruction within reasonable time
  → AG enforcement only (no private right of action)
  → Penalties: $25,000 per violation

Other US states (2026):
  → Washington, Colorado, Connecticut, Virginia, Montana, Oregon,
    Maryland, New York City (tenant biometrics)
  → Most require consent and retention/destruction policies
  → Trend: more states adding private right of action

International:
  → Brazil LGPD: sensitive data, explicit consent
  → India DPDP: significant data fiduciary obligations
  → Canada PIPEDA: meaningful consent required
  → South Africa POPIA: special personal information
```

## Engineering requirements

```
Collection:
  □ Written, informed consent collected BEFORE biometric capture
  □ Consent specifies: purpose, duration, method of destruction
  □ Consent is separate (not buried in ToS or privacy policy)
  □ Consent records stored with timestamps and version

Storage:
  □ Biometric templates stored separately from PII
  □ Encrypted at rest (AES-256 minimum)
  □ Encrypted in transit (TLS 1.3)
  □ Access controls: principle of least privilege
  □ No biometric data in logs, analytics, or error reports
  □ Template storage, not raw biometric data

Retention and destruction:
  □ Written retention schedule (publicly available for BIPA)
  □ Auto-deletion when purpose is fulfilled OR 3 years (BIPA)
  □ Destruction verification: confirm deletion from all stores
  □ Deletion includes backups (within backup rotation window)
  □ Audit log of destruction events

Processing:
  □ On-device processing preferred (no server transmission)
  □ If server-side: ephemeral processing, no persistent storage
  □ One-way hashing/template extraction (no raw biometric recon)
  □ No biometric data shared with third parties
  □ No profiling or analytics on biometric data
```

## Architecture patterns

```
Pattern 1: On-device biometric (preferred)
  User's device → local biometric API → match result (yes/no)
  Server receives: authentication result only, never biometric data
  Example: Face ID / Touch ID via WebAuthn
  BIPA exposure: minimal (no collection by your service)

Pattern 2: Template-based server matching
  Device → extract template → encrypt → server → compare → result
  Server stores: encrypted biometric template
  BIPA exposure: full (you possess biometric identifiers)

Pattern 3: Third-party biometric service
  Device → third-party API → match result
  Your server: no biometric data touches your infrastructure
  BIPA exposure: shared with processor (DPA required)
  Caution: you may still be liable as data controller
```

```javascript
// Preferred: WebAuthn biometric authentication (no biometric data leaves device)
const credential = await navigator.credentials.create({
  publicKey: {
    challenge: serverChallenge,
    rp: { name: 'My App', id: 'example.com' },
    user: {
      id: userId,
      name: userEmail,
      displayName: userName,
    },
    authenticatorSelection: {
      authenticatorAttachment: 'platform',
      userVerification: 'required', // triggers Face ID / fingerprint
    },
    pubKeyCredParams: [
      { type: 'public-key', alg: -7 },   // ES256
      { type: 'public-key', alg: -257 }, // RS256
    ],
  },
});
// Server receives: public key + attestation
// Server never receives: fingerprint, face scan, or biometric template
```

## Consent implementation

```javascript
// BIPA-compliant consent flow
async function collectBiometricConsent(userId) {
  const consentRecord = {
    userId,
    timestamp: new Date().toISOString(),
    consentVersion: '2.1',
    purpose: 'Identity verification for account access',
    dataCollected: 'Facial geometry template',
    retentionPeriod: '3 years or until account deletion',
    destructionMethod: 'Cryptographic erasure and record deletion',
    thirdPartySharing: 'None',
    consentMethod: 'explicit_click', // not pre-checked, not bundled
  };

  await db.biometricConsents.insert(consentRecord);
  await auditLog.record({
    action: 'biometric_consent_collected',
    userId,
    consentVersion: consentRecord.consentVersion,
  });

  return consentRecord;
}
```

## Anti-patterns

- **Bundling biometric consent in Terms of Service** — BIPA
  requires separate, specific written consent for biometric data
  collection. Burying biometric consent in a general ToS is not
  valid informed consent.
- **Storing raw biometric data** — storing full facial images,
  fingerprint scans, or voice recordings instead of mathematical
  templates. Raw data has higher re-identification risk and is
  harder to defend. Extract and store templates only.
- **No retention/destruction schedule** — BIPA requires a publicly
  available written policy specifying retention duration and
  destruction timeline. Without this, you violate BIPA even if
  your technical controls are otherwise sound.
- **Using biometrics for analytics** — analyzing biometric data
  for demographics, emotions, or behavioral patterns beyond the
  stated consent purpose. This violates purpose limitation
  principles under both BIPA and GDPR.

## Gotchas

- **Per-scan damages under BIPA** — the Illinois Supreme Court
  ruled that each biometric scan (not just initial collection)
  can constitute a separate violation. An employee scanned daily
  for 2 years = 500+ violations × $1,000-$5,000 each.
- **BIPA applies to companies outside Illinois** — any company
  that collects biometric data from Illinois residents is subject
  to BIPA, regardless of where the company is headquartered.
  Geographic filtering by user location is essential.
- **Derived biometric data** — templates, hashes, and mathematical
  representations of biometric data are still biometric identifiers
  under BIPA. Hashing does not exempt you from consent and
  retention requirements.
- **Vendor liability** — using a third-party biometric service does
  not eliminate your liability. As the entity determining the
  purpose of collection, you remain a data controller (GDPR) and
  may be jointly liable under BIPA.

## Verification

- Written biometric consent is collected before any biometric capture.
- Retention/destruction policy is publicly accessible.
- Biometric templates are encrypted at rest and in transit.
- Auto-deletion executes when retention period expires.
- Audit logs track collection, access, and destruction events.
- On-device processing is used where possible (WebAuthn/FIDO2).
- No raw biometric data is stored — templates only.

## Related

- `documentation/docs/policies/security/passkeys-webauthn-fido2.md`
- `documentation/docs/policies/compliance/data-retention-policy-engineering.md`
- `documentation/docs/policies/issues/gdpr-article-22-automated-decisions-2026.md`

## Source URLs (verified 2026-08-16)

- Privacy and Compliance in 2026: Biometric Authentication — https://keyless.io/blog/post/privacy-and-compliance-in-2026-why-biometric-authentication-will-change
- Biometric Data Privacy Laws: BIPA, GDPR & Global Compliance — https://liminal.co/articles/navigating-biometric-data-regulations/
- Biometric Data in Focus: BIPA and State Laws 2026 — https://www.venable.com/insights/publications/2026/07/biometric-data-in-focus-what-businesses-need
- Biometric Privacy Laws by State 2026 — https://ratedwithai.com/blog/biometric-privacy-laws-by-state-ai-2026
