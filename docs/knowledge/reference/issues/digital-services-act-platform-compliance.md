# Digital Services Act (DSA) Platform Compliance Engineering

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your platform has 50 million monthly active EU users, qualifying it
as a VLOP (Very Large Online Platform). The European Commission opens
formal proceedings requesting your transparency database submissions,
annual risk assessment, and researcher data access mechanisms. Your
engineering team discovers that content moderation decisions lack
machine-readable Statements of Reasons, your ad repository does not
meet the 24-hour update requirement, and you have no API for trusted
flaggers. The first DSA fine — 120 million EUR against X in December
2025 — demonstrates that enforcement is real and the penalties are
substantial.

## Context

The Digital Services Act entered full enforcement in 2025-2026. As of
July 2025, new harmonized transparency reporting templates are
mandatory. Platforms must submit Statements of Reasons (SoR) for
every content moderation decision to the EU Transparency Database.
VLOPs (45+ million monthly active EU users) face additional
obligations: annual risk assessments, independent audits, algorithmic
transparency, recommender system disclosure, and researcher data
access. The first fine (X, 120M EUR, December 2025) targeted
deceptive design, ad repository deficiencies, and blocking researcher
access.

## Transparency Database API

```
Endpoints:
  POST /api/v1/statement           Single Statement of Reasons
  POST /api/v1/statements          Batch (max 100 per call)
  GET  /api/v1/statement/existing-puid/<PUID>  Check PUID uniqueness

Authentication:
  Authorization: Bearer YOUR_TOKEN
  Accept: application/json
  Content-Type: application/json

Tokens generated via user profile; each new token invalidates prior.
```

```
Statement of Reasons required fields:

  decision_visibility/monetary/    At least one decision type
  provision/account

  decision_ground                  ILLEGAL_CONTENT or
                                   INCOMPATIBLE_CONTENT

  content_type                     APP, AUDIO, IMAGE, PRODUCT,
                                   SYNTHETIC_MEDIA, TEXT, VIDEO, OTHER

  category                         16 predefined categories

  source_type                      ARTICLE_16, TRUSTED_FLAGGER,
                                   OTHER_NOTIFICATION, VOLUNTARY

  automated_detection              Yes/No
  automated_decision               FULLY, PARTIALLY, NOT_AUTOMATED

  puid                             Platform-unique identifier
                                   (alphanumeric + hyphens, max 500)

  territorial_scope                ISO country codes (EU/EEA)
  decision_facts                   Max 5000 characters
  application_date                 YYYY-MM-DD, >= 2020-01-01

Conditional: if ILLEGAL_CONTENT, must supply
  illegal_content_legal_ground and illegal_content_explanation

Responses:
  201 Created (success, returns uuid + permalink)
  401 Unauthorized
  422 Unprocessable (validation errors per field)
  302 Found (PUID conflict with existing statement)
```

## VLOP obligations

```
Platforms with 45+ million monthly active EU users:

Risk Assessments (annual):
  → Document how algorithms contribute to systemic risks
  → Illegal content dissemination
  → Fundamental rights violations
  → Public discourse manipulation
  → Harms to minors

Independent Audits (annual):
  → Third-party assessment of DSA compliance
  → Algorithmic transparency review
  → Risk mitigation adequacy

Recommender System Transparency (Article 27):
  → Disclose main parameters in plain language
  → Explain content suggestion logic
  → Offer non-profiling recommender option

Researcher Data Access (Article 40):
  → Vetted researchers get non-public data access
  → Must explain algorithm design, logic, functioning, testing

Ad Repository (Article 39):
  → Searchable, real-time ad transparency repository
  → Update within 24 hours
```

## Trusted flaggers (Article 22)

```
Organizations certified by Digital Services Coordinators with
expertise in identifying illegal content.

Platform obligations:
  → Priority processing of trusted flagger reports
  → Set source_type: TRUSTED_FLAGGER in SoR
  → No standardized cross-platform API exists (mid-2026)
  → Each platform implements own mechanism per Article 16

Article 44(1)(c) provides legal basis for harmonized API,
but Commission has not yet mandated a standard.
```

## Out-of-court dispute resolution (Article 21)

```
Process:
  1. User exhausts Article 20 internal appeals
  2. User submits dispute to certified ODS body
  3. Platform retains disputed content for minimum 6 months
  4. Platform supplies SoR per Article 17(1)
  5. ODS body issues non-binding decision
  6. Platform bears ODS costs (even if user loses)

User may be charged nominal submission fee, reimbursed on success.
Platform must use Platform Unique Identifiers for tracking.
```

## Anti-patterns

- **Treating SoR as an afterthought** — Statements of Reasons must
  be generated for every content moderation decision. Retrofitting
  this onto existing moderation systems is expensive. Build SoR
  generation into the moderation pipeline from the start.
- **Batch submission without validation** — a single invalid statement
  in a 100-item batch rejects the entire batch atomically. Validate
  each statement before batching.
- **Deprioritizing researcher data access** — X's 120M EUR fine was
  partly for blocking researcher access. This obligation is audited
  and enforced.
- **Vague automated moderation reporting** — must report both accuracy
  rates and error rates of automated systems. Missing or vague data
  triggers enforcement scrutiny.

## Gotchas

- **Batch atomicity** — the API rejects entire batches if any single
  statement fails validation. Pre-validate all statements individually
  before submitting as a batch.
- **PUID collisions** — conflicts return 302 Found, not a clear error.
  Check uniqueness via the PUID endpoint before submission.
- **Recommender transparency does not require revealing weights** —
  Article 27 requires disclosing main parameters in plain language,
  not exact algorithmic weights or every parameter.
- **ODS decisions are non-binding** — but platforms must participate
  and bear costs. Design dispute resolution workflows that handle
  the full lifecycle from appeal through ODS resolution.
- **First enforcement precedents** — X fine (120M EUR, Dec 2025),
  Shein proceedings (Feb 2026), Grok AI investigation (Feb 2026).
  Enforcement targets both large obvious violations and emerging
  AI-related risks.

## Verification

- SoR generated for every content moderation decision.
- Transparency Database submissions pass validation before batching.
- PUID uniqueness checked before statement submission.
- Risk assessment completed and documented annually.
- Researcher data access mechanism operational and tested.
- Ad repository updates within 24 hours of ad serving.

## Related

- `documentation/docs/policies/issues/eu-ai-act-risk-classification-compliance.md`
- `documentation/docs/policies/issues/dark-patterns-deceptive-design-regulation.md`
- `documentation/docs/policies/compliance/privacy-enhancing-technologies-pets.md`

## Source URLs (verified 2026-08-16)

- DSA Transparency Database API Documentation — https://transparency.dsa.ec.europa.eu/page/api-documentation
- Overview of DSA Developments Nov 2025 - Feb 2026 — https://eucrim.eu/news/overview-of-the-latest-developments-under-the-digital-services-act-november-2025-february-2026/
- DSA Content Moderation Requirements — https://getstream.io/blog/dsa-moderation-requirements/
- DSA Algorithmic Transparency — https://www.freshfields.com/en/our-thinking/blogs/technology-quotient/dsa-decoded-10-algorithmic-transparency-under-the-dsa-102mgg8
