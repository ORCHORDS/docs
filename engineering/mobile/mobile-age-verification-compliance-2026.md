# mobile-age-verification-compliance-2026

**Issue:** U.S. state "App Store Accountability Acts" and EU rules taking effect 2026–2027 require age verification and age-appropriate safeguards from both app stores and developers
**Date:** 2026-08-12
**Status:** documented

## Symptom / Context
As of 2026, four U.S. states (Texas, Utah, Arkansas, Louisiana, with more pending) have
enacted App Store Accountability laws. Apple and Google must perform age assurance at the
account level, but **developers are jointly responsible** for: declaring their app's age
rating accurately, implementing age-appropriate experiences, gating mature content, and
honoring parental-consent signals. The EU is moving toward a similar framework. Apps that
ignore this face removal and per-state fines.

## Pattern / Solution

**1. Accurate age rating (declared, not detected):**
- iOS: App Store Connect → "Age Rating" questionnaire. Drive it from real content, not
  defaults. An incorrect rating is the most common cause of post-launch removal.
- Android: Play Console → "Content rating" via IARC questionnaire. Re-run it whenever you
  add user-generated content, live chat, or gambling/loot-box features.

**2. Respect the store-provided age signal:**
```kotlin
// Android — Device Framework signals the account age band
// Apps should gate on Google Play's declared age, not re-prompt unnecessarily
```
```swift
// iOS — use the App Store's age declaration; avoid collecting DOB yourself
// unless you have a documented legal basis (GDPR/KSAs require it).
```
Do **not** build your own ID-scan / government-ID flow unless you are a regulated
business (age-restricted commerce, social with UGC + minors). Those flows carry data-
retention legal obligations that most apps cannot meet.

**3. Gate mature content server-side, not client-side:**
```ts
// Backend middleware: trust the age band from the store attestation token,
// never the client-supplied age value.
router.use('/mature-content', (req, res, next) => {
  const ageBand = req.storeToken?.ageBand; // 'child' | 'teen' | 'adult'
  if (ageBand !== 'adult') return res.status(403).json({ error: 'AGE_RESTRICTED' });
  next();
});
```

**4. Default-to-safe for teens:**
- Direct messaging, livestream, and discovery feeds OFF by default for under-16 accounts.
- Provide a parental-controls surface even when not legally mandated — reviewers check.

**5. Document your data flows:**
Keep a written record of what age data you receive, from whom, retention period, and who
can access it. Regulators ask for this during investigation.

## Gotchas
- The store age signal is **per-account, not per-device**. Shared family devices with a
  parent + child logged into the same account will deliver the adult band to both — you
  must support an in-app parental override, not blindly trust the band.
- Collecting a user's date of birth "just to check" makes you a data controller under
  GDPR and most U.S. state privacy laws. Prefer the store signal; collect DOB only if you
  have a lawful basis and a deletion workflow.
- Apple's App Review in 2026 is rejecting apps that show age-inappropriate ads in a teen-
  rated context. Audit your ad SDK's floor categories, not just your own content.
- State laws differ on the exact cutoff (16 in some, 18 in others). Use the most
  restrictive threshold as your single gate; do not try to geo-detect and vary behavior —
  VPN users will defeat that and you'll be on the hook.
- App Store Connect lets you change the age rating after submission, but a downgrade
  (adult → teen) triggers a full re-review and can pull your live binary offline for days.
- The "Kids" category on iOS has a separate, stricter review track. A general-audience
  app does NOT belong there — submitting to Kids to broaden reach backfires.
- Parental consent flows for under-13 (COPPA) are a separate, federal regime layered on
  top of the state laws. Treat under-13 as its own hard wall.
- Play Integrity / App Attest tokens now carry an age-band claim in 2026 — verify the
  token server-side before trusting it; a raw client payload is trivially forged.

## Related
- `play-integrity-attestation.md`
- `cross-platform-app-attestation-device-integrity.md`
- `mobile-gdpr-mobile.md`
- `app-store-policy-hotspots-2026.md`
- `mobile-penetration-testing-2026.md`
