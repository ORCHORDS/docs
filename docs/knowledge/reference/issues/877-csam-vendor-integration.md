# 877 — CSAM vendor integration

**Issue:** the platform must integrate with a vendor for CSAM/NCII detection and NCMEC reporting
**Date:** 2026-08-09
**Repo:** <your-org>/<your-repo> at main
**Author:** the platform team
**Status:** open (genuinely blocked on vendor process)

## Symptom
the platform allows user-generated content (UGC). The platform must:
1. Detect known CSAM (Child Sexual Abuse Material) via hash matching
2. Detect NCII (Non-Consensual Intimate Imagery) via perceptual hashing
3. Report confirmed CSAM to NCMEC (National Center for Missing &
   Exploited Children) within 24h of detection
4. Remove + preserve evidence for law enforcement

## Root cause
This is not a code issue — it's a vendor onboarding issue. The
platform needs to choose a CSAM detection vendor, sign their
agreement, integrate their API, and configure NCMEC reporting.

**Source:**
- 18 U.S.C. § 2258A (federal reporting requirement)
- Apple App Store Review Guidelines 1.4 + 5.1.1
- Google Play User-Generated Content policy
- NCMEC reporting portal: https://report.cybertip.org/

**the platform's compliance need:** a 21+ social platform must meet
higher standards than 13+ platforms. Apple + Google both
specifically call out 18+ social apps in their CSAM guidelines.

## What needs to happen

1. **Vendor selection** — likely candidates: Thorn (https://www.thorn.org),
   PhotoDNA (Microsoft), or Hive. Thorn is free for non-profits;
   PhotoDNA is free for qualified CSAM detection.
2. **MSA + DPA signed** — vendor agreement + data processing addendum
3. **Sandbox API key** — vendor provides test environment
4. **Integration code** — hash every uploaded image, check against
   vendor's hash database, flag matches
5. **NCMEC CyberTipline API** — separate integration; report format
   per NCMEC spec
6. **Evidence preservation** — when CSAM is detected, preserve
   the file + metadata for 90 days (NCMEC's retention requirement)
7. **Operator training** — on-call staff must know how to escalate
   confirmed matches

## Why it's blocked

The vendor process requires:
- Legal review (vendor MSA, liability, jurisdiction)
- Procurement (billing setup, even for free tiers)
- Security review (vendor's data handling, encryption, access)
- Sandbox testing (verify false positive rate acceptable)

None of this is a code change. The code can be written in parallel
using a stubbed vendor interface (`lib/csam.ts` with a
`checkHash(image) → match | no-match` signature), but the real
integration waits for vendor onboarding.

## Workarounds in place

- **the platform has a stub `lib/csam.ts`** that always returns
  `no-match`. This lets the rest of the platform build around the
  interface without blocking.
- **Content moderation queue** in `apps/web/src/lib/moderation.ts`
  flags user-reported content for human review. This is the
  fallback path when the vendor is unavailable.
- **Block list** for known-bad users (e.g. previously banned for
  other ToS violations) is in place via the trust & safety module.

## Related
- the platform issue #open-issue-csam (this issue)
- the platform issue #open-issue-ncmec (NCMEC ESP registration)
- the platform issue #open-issue-dmca (DMCA designated agent)
- the platform issue #open-issue-compliance-epic (T&S compliance epic — this issue is a
  sub-task of #open-issue-compliance-epic)
- Compliance master plan: `docs/COMPLIANCE-STANDARD.md` (also
  referenced in a sibling repo #1057)
