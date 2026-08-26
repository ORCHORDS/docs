# dma-platform-designation

**Issue:** EU Digital Markets Act — gatekeeper designation
**Date:** 2026-08-09
**Status:** documented (compliance checklist)

## Symptom
Your platform is a "core platform service" under the DMA. The
European Commission designates you as a gatekeeper. You have 6
months to comply. You have 25 obligations. Some require deep
architectural changes.

## Root cause
The Digital Markets Act (DMA) targets "gatekeeper" platforms —
the ones with the biggest market power. A platform is a
gatekeeper if it meets quantitative thresholds (e.g. €7.5B
market cap, 45M EU users) OR is designated by the Commission.

**Source:** DMA text:
https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R1925

> "Gatekeeper platforms shall ensure and demonstrate compliance
> with the obligations set out in this Regulation."

## When does it apply?

Designated gatekeepers (as of 2024): Alphabet (Google), Amazon,
Apple, ByteDance (TikTok), Meta, Microsoft.

For a 21+ social platform with EU users, you're likely NOT a
gatekeeper (the thresholds are very high). But:
- **App stores** that distribute your app are gatekeepers
- **App developers** must comply with the obligations
  (anti-steering, fair ranking, etc.) imposed on the app
  stores

## The 25 obligations (Article 5, 6, 7)

### Article 5: Self-executing obligations
1. **No combining personal data** across core platform services
   without consent
2. **Allow third-party services** to interoperate (e.g. allow
   third-party app stores on Android)
3. **Allow users to un-install pre-installed apps**
4. **Allow side-loading** of apps
5. **No self-preferencing** in ranking (Google Shopping can't
   rank its own products higher)
6. **No tying** of services (can't require Chrome to use
   Google Search)
7. **Transparency in ad pricing** (publish ad pricing data)
8. **Transparency in active user numbers** (publish monthly
   active users)
9. **No anti-competitive data practices** (no scraping,
   no piggy-backing)
10. **Allow porting of data** (e.g. social graph export)

### Article 6: Obligations subject to further specification
11. **Non-discrimination** in app store rankings
12. **Allow alternative payment systems** (in-app purchases
    via Stripe, not just Apple Pay)
13. **Allow alternative app distribution**
14. **Interoperate with third-party services** (e.g. WhatsApp
    interoperability with iMessage)
15. **No self-preferencing in app store search**
16. **Allow users to choose default browser, search engine, etc.**
17. **End-to-end encryption for messaging** (or document why
    not)

### Article 7: Messaging interoperability
18. **Provide APIs for interoperable messaging**
19. **Publicly document the APIs**
20. **Free of charge for the interoperating service**

## What this means for your platform

If your platform is NOT a gatekeeper, the DMA is indirect:
- **You may be required to interoperate** with a gatekeeper's
  platform (e.g. a "share to [your platform]" button on
  iMessage)
- **You benefit from the gatekeeper's obligations** (e.g. you
  can distribute via third-party app stores on Android, with
  0% commission)
- **You have NO obligations** under the DMA itself

If your platform IS a gatekeeper (rare for a 21+ social
platform):
- 25 obligations to implement
- 6 months from designation
- Non-compliance fines: up to 10% of global turnover, or 20%
  for repeat offenders

## Fix (if you're a gatekeeper)

### 1. Conduct the gatekeeper assessment
- Document why you meet (or don't meet) the thresholds
- If you meet them, notify the Commission

### 2. Implement the obligations
For each obligation:
- **Design the technical solution** (e.g. side-loading on
  Android)
- **Implement the change** (significant engineering work)
- **Document the implementation** for the Commission's audit
- **Submit a compliance report** annually

### 3. Compliance monitoring
- The Commission monitors compliance
- Non-compliance triggers investigation + fines
- Engage external counsel (the DMA is a new regulation; few
  in-house teams have deep expertise)

## What to track

### Per-Article compliance
- A tracking spreadsheet: per-Article, per-Obligation, status
- Engineering tickets for the technical changes
- Legal review for the policy changes

### Annual compliance report
- Submit to the Commission
- Public (the Commission publishes summaries)
- Detail: how you implemented each obligation, evidence of
  compliance

## Verification
- **Test:** Each obligation has a corresponding test or
  control
- **Live:** The platform complies (e.g. users can un-install
  pre-installed apps)
- **Audit:** Annual third-party review of DMA compliance

## Gotchas
- **The DMA is in addition to, not instead of, GDPR.** Both
  apply.
- **Designation can be appealed.** But the appeal process is
  slow, and you must comply during the appeal.
- **Some obligations are easier to comply with than others.**
  "No self-preferencing" is hard to test; "allow side-loading"
  is easy to test.
- **The 10% global turnover fine is for the GROUP, not just
  the platform.** For a multi-product company, the fine
  applies to total revenue.
- **The DMA has an extraterritorial scope.** Even non-EU
  platforms with EU users are subject to the DMA.

## Related
- `compliance/region-matrix.md` (where the DMA applies)
- `gdpr-article-17-erasure.md` (related EU regulation)
- DSA: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2065
- DMA: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R1925
