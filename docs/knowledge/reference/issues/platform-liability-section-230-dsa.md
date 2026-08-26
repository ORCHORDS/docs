# Platform Liability — Section 230 and DSA

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A third party sues after a user posts defamatory content. A
European regulator demands removal of illegal content within
24 hours under DSA Article 17. The legal team asks: what is the
platform actually liable for, and what does moderation (or its
absence) do to that liability? The answer differs by
jurisdiction — and the US and EU frameworks push in opposite
directions on proactive moderation.

## Context

example project hosts user-generated content but does not create it.
Two legal regimes govern liability: Section 230 of the US
Communications Decency Act and the EU Digital Services Act.
Both share a "passive host" safe harbor concept but diverge
sharply on notice obligations, proactive moderation risk, and
what platform behavior destroys immunity.

## Section 230 safe harbor (US)

```
47 U.S.C. § 230 conditions:

  Protected if:
    1. Platform is an "interactive computer service provider"
    2. Content was provided by a third-party user
    3. Claim treats the platform as publisher of that content

  Carve-outs (§ 230 does NOT cover):
    → Federal criminal law (CSAM — 18 U.S.C. § 2258A)
    → FOSTA-SESTA (sex trafficking facilitation)
    → Intellectual property (DMCA governs separately)
    → Electronic communications privacy (ECPA)

  Proactive moderation + § 230:
    → § 230(c)(2) explicitly protects good-faith removal
    → Removing content does NOT destroy § 230 immunity
    → "Editing" user content is riskier than removing it
    → Courts have consistently rejected "moderating = publisher"
```

## EU Digital Services Act hosting liability

```
DSA liability framework (Art. 6):

  Safe harbor if:
    (a) Platform lacks actual knowledge of illegality, OR
    (b) Platform acts expeditiously after gaining knowledge

  "Actual knowledge" triggers:
    → Receipt of a compliant Art. 16 notice
    → Platform's own detection discovers illegal content
    → Order from a competent authority

  Art. 8 — no general monitoring obligation:
    → Regulators CANNOT mandate general monitoring
    → Voluntary detection is permitted and encouraged
    → Once detected, the platform MUST act expeditiously
    → Failing to act on detected content removes immunity
```

## Notice and takedown

```
DSA Art. 16 — valid notice must include:
  → URL(s) of specific content
  → Why the content is illegal (legal basis)
  → Name and contact of notifier
  → Good-faith declaration

Platform obligations on receipt:
  → Acknowledge promptly
  → Assess and decide
  → Notify notifier of outcome
  → If removed: Statement of Reasons (Art. 17) filed
    to EU Transparency Database
  → Submit SoR per Art. 17 to transparency DB

Timelines:
  → No hard statutory deadline for most content
  → "Expeditiously" is the standard
  → Terrorist content: 1 hour (TCOR, separate regulation)
```

## VLOP vs. smaller platform obligations

```
All hosting platforms (Arts. 16/17/20/21/24):
  → Notice-and-takedown + Statement of Reasons
  → Internal complaint-handling
  → Out-of-court dispute resolution access
  → Annual transparency reporting

VLOPs only (45M+ monthly active EU users):
  → Annual risk assessments (Art. 34)
  → Independent audits (Art. 37)
  → Researcher data access (Art. 40)
  → Ad repository (Art. 39)
  → Real-time crisis response mechanism (Art. 48)

example project below VLOP threshold:
  → Arts. 16/17/20/21/24 apply now
  → VLOP obligations do NOT apply unless threshold crossed
```

## Anti-patterns

- **Believing proactive moderation destroys § 230** — § 230(c)(2)
  explicitly protects good-faith removal. The "moderating =
  publisher" theory has been consistently rejected by US courts.
- **Treating the DSA as a US law** — DSA applies to platforms
  offering services in the EU regardless of incorporation
  location.
- **Waiting for a notice before removing detected content** —
  once the platform detects illegal content, "actual knowledge"
  is established and the prompt-action duty attaches.
- **Conflating DMCA with DSA notice-and-takedown** — DMCA § 512
  covers only copyright. DSA Art. 16 covers all illegal content
  under EU law. One policy does not satisfy both.

## Gotchas

- **FOSTA-SESTA carved out of § 230** — platforms can be civilly
  and criminally liable for knowingly facilitating sex
  trafficking regardless of the UGC nature of the content.
- **DSA "illegal content" is defined by EU member state law** —
  what is illegal in Germany (Holocaust denial) may be lawful
  in the US. Decisions must be jurisdiction-specific.
- **Statement of Reasons must be filed in EU Transparency DB**
  for every moderation decision affecting EU users — not just
  VLOPs.
- **Gonzalez v. Google (2023)** left algorithm recommendation
  liability under § 230 unresolved. Anonymous platforms with
  non-personalized feeds carry lower algorithm risk.

## Verification

- Notice-and-takedown pipeline generates Statements of Reasons
  per Art. 17 for all EU-user content decisions.
- Internal appeal mechanism (Art. 20) is operational.
- FOSTA-SESTA screening is separate from general content policy
  and is not contingent on notice receipt.
- Legal counsel has confirmed merchant-only payment model does
  not create additional FOSTA-SESTA risk.

## Related

- `documentation/docs/policies/issues/anonymous-platform-abuse-prevention.md`
- `documentation/docs/policies/issues/digital-services-act-platform-compliance.md`
- `documentation/docs/policies/issues/dsa-risk-assessment.md`
- `documentation/docs/policies/issues/user-privacy-law-enforcement-requests.md`
- `documentation/docs/policies/issues/877-csam-vendor-integration.md`

## Source URLs (verified 2026-08-17)

- 47 U.S.C. § 230 full text
  — https://www.law.cornell.edu/uscode/text/47/230
- DSA full text (Art. 6 hosting liability) — EUR-Lex
  — https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2065
- EFF Section 230 explainer
  — https://www.eff.org/issues/cda230
- FOSTA-SESTA (Pub. L. 115-164)
  — https://www.congress.gov/bill/115th-congress/senate-bill/1693
- Stanford Internet Observatory — DSA vs. § 230 comparison
  — https://cyber.fsi.stanford.edu/io/news/comparing-section-230-and-eu-dsa
