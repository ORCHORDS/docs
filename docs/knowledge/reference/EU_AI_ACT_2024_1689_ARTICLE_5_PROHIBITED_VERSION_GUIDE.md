---
title: "EU AI Act — Article 5 Prohibited Practices Version Guide"
standard: EU Regulation 2024/1689 Article 5
publisher: European Parliament and Council
category: reference
subcategory: ai-governance
canonical_url: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1689
status: approved
classification: public
audience: ai-governance, legal, security-engineering, product
last-reviewed: 2026-09-05
review-cycle: 12 months
next-review: 2027-09-05
---

## Scope

Article 5 of the EU AI Act prohibits certain AI practices outright. Deploying
or placing on the market an AI system that performs a prohibited practice is
unlawful under EU law and triggers administrative fines under Article 99.

This guide enumerates the prohibited practices, gives ORCHORDS-side screening
criteria, and explains the application date and penalty framework.

## Identifier Table

| Field | Value |
| --- | --- |
| Instrument | Regulation (EU) 2024/1689 |
| Article | 5 |
| Title | Prohibited AI practices |
| Entry into force | 2 February 2025 |
| Companion | Article 99 (penalties), Article 6 (high-risk), Recital 28–32 |

## Plan

ORCHORDS treats Article 5 as a hard gate in the AI intake process. Before any
build or deployment the use case must be screened against Article 5:

1. Confirm no subliminal techniques, manipulative exploitation, or material
   distortion of behaviour.
2. Confirm no exploitation of vulnerabilities due to age, disability, or
   socio-economic situation.
3. Confirm no social scoring by public or private actors leading to
   detrimental or unfavourable treatment.
4. Confirm no real-time remote biometric identification in publicly
   accessible spaces for law enforcement (with documented exceptions).
5. Confirm no biometric categorisation inferring race, political opinions,
   trade union membership, religion, sex life, or sexual orientation.
6. Confirm no untargeted scraping of facial images from the internet or CCTV
   to build or expand facial recognition databases.
7. Confirm no emotion recognition in workplace and education contexts
   (exceptions: medical or safety reasons).
8. Confirm no biometric verification of sensitive attributes.
9. Confirm no individual risk profiling leading to unjustified detrimental
   treatment based solely on profiling.

## Inputs

- AI use case intake form.
- Target user group and demographic screen.
- Deployment context (workplace, education, public space, law enforcement).
- Data sources and provenance.

## ORCHORDS Profile Table

| Practice | Screen test | ORCHORDS default |
| --- | --- | --- |
| Subliminal manipulation | Intent + effect on behaviour | Block |
| Vulnerability exploitation | Knowledge of impaired autonomy | Block |
| Social scoring | Detrimental treatment beyond context-appropriate | Block |
| Real-time biometric ID (law enforcement) | Public space + law enforcement + no exception | Block |
| Sensitive biometric categorisation | Sensitive attributes beyond biometric matching | Block |
| Untargeted facial scraping | Untargeted facial data from internet/CCTV | Block |
| Emotion recognition (work/edu) | Outside medical or safety | Block |
| Predictive policing on profiling alone | Sole reliance on profiling | Block |

## Implementation Notes

- Article 5 exceptions are narrow; ORCHORDS does not assume an exception
  applies unless the responsible authority and documented procedure both
  support it.
- Penalties under Article 99 can reach EUR 35 million or 7 % of worldwide
  annual turnover for prohibited-practice violations.
- The screen is a pre-condition to any AIMS risk treatment; the output is
  stored in the AI risk register with evidence.

## Companion Documents

- EU AI Act Reference Card
- EU AI Act — Annex III Reference Card
- EU AI Act — GPAI Obligations Reference Card
- OECD AI Principles Reference Card
- NIST AI 100-1 Reference Card
