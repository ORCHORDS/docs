# store-region-matrix

**Issue:** Apple App Store + Google Play region restrictions
**Date:** 2026-08-09
**Status:** documented (architectural decision)

## Symptom
You ship a social platform to the App Store. Apple's reviewer
in Saudi Arabia rejects the app because it allows 18+ content.
You add region restrictions. Google Play rejects the same
config because Saudi Arabia is on their restricted list. You
have a 6-region matrix of overrides.

## Root cause
App Store and Play Store have different rules for adult content,
crypto, gambling, etc. The rules also change with political
events. Saudi Arabia, UAE, and China have specific restrictions
on adult content; some US states restrict certain content;
some EU countries require specific consent flows.

**Source:** Apple App Store Review Guidelines:
https://developer.apple.com/app-store/review/guidelines/

> "Apps must comply with all legal requirements in any location
> where they are made available."

For a 21+ social platform, the matrix is non-trivial.

## Fix
Maintain a **region matrix** in code:

```ts
// apps/web/src/lib/distribution.ts
export type RegionStatus = 'allowed' | 'blocked' | 'restricted' | 'ship-with-care';

export interface RegionConfig {
  code: string;  // ISO 3166-1 alpha-2
  status: RegionStatus;
  // Optional overrides per region
  requiresExplicitAge?: boolean;
  blocksCryptoFeatures?: boolean;
  blocksAdultContent?: boolean;
  requiresLocalRepresentative?: boolean;
  notes?: string;
}

export const REGION_MATRIX: Record<string, RegionConfig> = {
  // US — federated rules, mostly OK
  'US': { code: 'US', status: 'allowed' },
  // 18+ states — some require explicit age
  'US-LA': { code: 'US-LA', status: 'restricted', requiresExplicitAge: true },
  'US-MT': { code: 'US-MT', status: 'restricted', requiresExplicitAge: true },

  // EU — GDPR applies, GDPR-compliant regions
  'DE': { code: 'DE', status: 'allowed' },
  'FR': { code: 'FR', status: 'allowed' },

  // UK — GDPR + local law
  'GB': { code: 'GB', status: 'allowed' },

  // Saudi Arabia — adult content blocked
  'SA': {
    code: 'SA',
    status: 'blocked',
    blocksAdultContent: true,
    notes: 'Adult content prohibited. App not listed in SA App Store.',
  },

  // UAE — adult content blocked
  'AE': {
    code: 'AE',
    status: 'blocked',
    blocksAdultContent: true,
  },

  // China — internet restrictions, requires local rep
  'CN': {
    code: 'CN',
    status: 'blocked',
    notes: 'Internet content licensing required. App not listed.',
  },

  // Japan — adult content allowed with explicit age gate
  'JP': {
    code: 'JP',
    status: 'ship-with-care',
    requiresExplicitAge: true,
  },

  // India — content moderation strict
  'IN': {
    code: 'IN',
    status: 'ship-with-care',
    notes: 'IT Rules 2021 compliance — grievance officer + content moderation.',
  },
};
```

## Per-platform (App Store vs Play Store vs Web)

The matrix applies DIFFERENTLY to each distribution channel:

### App Store (iOS)
- Region restrictions are enforced by Apple, not by you
- You declare `LSApplicationCategoryType` + the content rating
- Apple blocks distribution to blocked regions
- You DON'T need to runtime-restrict content (Apple has already
  blocked the app)

### Play Store (Android)
- Region restrictions enforced by Google, with more granular
  per-country controls
- You declare target audience + content rating
- Google blocks distribution to blocked regions
- Same: no runtime check needed

### Web (PWA)
- Region restrictions are YOUR responsibility
- The web app loads for any user
- You MUST runtime-check the region and adjust UI/feature set
  (e.g. block adult content, force explicit age gate, etc.)
- Use IP geolocation (CF `cf-ipcountry` header is one source;
  MaxMind is another)

## Drift detection

The matrix must be in sync between:
- `apps/web/src/lib/distribution.ts` (web runtime)
- `functions/src/lib/distribution.ts` (CF Pages Functions)
- App Store / Play Store metadata (manual — checked by humans)

Add a CI check:
```bash
# In CI:
diff <(grep -E "^\s*'[A-Z]{2}'" apps/web/src/lib/distribution.ts | sort) \
     <(grep -E "^\s*'[A-Z]{2}'" functions/src/lib/distribution.ts | sort)
# Fail if mismatch
```

## Verification
- **Test:** `test/distribution.test.ts > 20 regions configured`
  — passes
- **Live:** Web app shows correct UI for US, JP, IN, SA users
- **Store review:** App Store + Play Store listings match the
  matrix

## Gotchas
- **The matrix changes often.** New sanctions, new laws, new
  store policies. Schedule a quarterly review.
- **IP geolocation is approximate.** A VPN user in DE may have
  a US IP. Use multiple signals (IP + Accept-Language + user
  preference).
- **The matrix is a compliance signal, not a security boundary.**
  A determined user can bypass via VPN. Use it for legal
  compliance, not for access control.
- **Children's regions (e.g. California under CCPA)** have
  separate rules layered on top of the region matrix.
- **EU "Digital Services Act" (DSA)** requires specific
  disclosures for VLOPs (Very Large Online Platforms). Add a
  transparency report page if you meet the threshold (45M EU
  users).

## Related
- `gdpr-article-17-erasure.md`
- `ccpa-opt-out.md`
- `compliance/apple-app-site-association.md` (separate from region
  matrix but related to distribution)
- Apple guidelines: https://developer.apple.com/app-store/review/guidelines/
