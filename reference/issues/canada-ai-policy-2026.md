# canada-ai-policy-2026

**Issue:** A US company plans to launch an AI system in Canada. The team researches "Canada AI law." They find references to AIDA. They build a compliance plan around AIDA. AIDA is dead. The real story is Bill C-36 + Quebec Law 25 + Ontario ESA, not a federal AI Act.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Canada has no horizontal federal AI statute as of mid-2026. AIDA died with Bill C-27 in January 2025. The 2026 framework is privacy law (PIPEDA, Bill C-36, Quebec Law 25) + sectoral rules (Ontario ESA, Ontario EDSTA) + voluntary federal strategy (AI for All).

## Root cause

Bill C-27 (June 2022) had 3 parts: CPPA (privacy), PIDPTA (tribunal), and AIDA (AI). Parliament prorogued January 2025; all 3 died. Bill C-36 (June 2026) revives CPPA as PPCDA but explicitly does NOT revive AIDA. The government has said AIDA will not return.

## The 5 active Canadian instruments (2026)

| Instrument | Status | Scope | Effective |
|---|---|---|---|
| Bill C-36 (PPCDA) | pending (second reading) | private-sector privacy; AI in privacy scope via "personal information" | TBD (not law) |
| Quebec Law 25 (modernized privacy) | law | private-sector privacy; automated decisions | September 22, 2023 |
| Ontario Employment Standards Act s. 8.4 | law | AI in hiring disclosure | January 1, 2026 |
| Ontario EDSTA (Bill 194) | law (selected sections) | public-sector AI duties | January 29, 2025 (AI in force) |
| Bill C-34 (Safe Social Media Act) | pending | AI chatbot duties | TBD |

The 5 instruments are layered: federal privacy (pending), provincial privacy + sectoral (in force), and federal sectoral (pending).

## The 3 key dates

- **January 6, 2025** — Bill C-27 died (including AIDA)
- **January 1, 2026** — Ontario ESA s. 8.4 (AI in hiring disclosure) in force
- **June 15, 2026** — Bill C-36 (PPCDA) introduced; AI not in name but in scope

The 3 dates anchor the timeline.

## The Quebec Law 25 automated decision rules

Quebec Law 25 (in force since September 2023) is the most concrete provincial AI rule.

- **Scope:** any decision based exclusively on automated processing of personal information
- **Right to be informed:** person must be informed at or before the decision
- **Right to reasons:** on request, must receive reasons, principal factors, parameters
- **Right to correction:** correction rights apply
- **Right to human review:** opportunity for human review

Quebec Law 25 is the de facto Canadian AI automated-decision rule until C-36 passes.

## The Ontario ESA s. 8.4 hiring rule

Since January 1, 2026, Ontario employers with 25+ employees must disclose AI use in publicly advertised hiring.

- **Scope:** covered employer using AI to screen, assess, or select applicants
- **Trigger:** publicly advertised position
- **Requirement:** disclosure in the posting
- **Threshold:** 25+ employees on the posting date
- **Exemption:** under 25 employees

A simple but enforceable rule. US companies hiring in Ontario must comply.

## The 4 things Bill C-36 changes for AI

Bill C-36 (PPCDA, June 2026) handles AI under privacy law, not AI law.

1. **Personal information includes inferred data.** "Information that is inferred about the individual" is now personal information. A credit score, propensity model, or churn prediction gets statutory protection.
2. **General account of automated decision systems.** Section 62: organizations must give a general account of any automated decision system that "could have a legal or similarly significant effect."
3. **Right to explanation on request.** Section 63: on request, provide the specific factors, data sources, and reasoning; route to human review.
4. **Restrictions on behavior-influencing systems.** Section 18(3): restricts using automated systems to influence behavior without consent.

The 4 changes are materially narrower than AIDA but create real obligations for AI in Canada.

## The 5-step compliance pattern

For a US/EU company launching an AI system in Canada.

1. **Map use cases** — identify which AI uses touch personal data and which affect legal/similar decisions
2. **If Quebec customers/employees** — Law 25 compliance: inform, reasons, correction, human review
3. **If Ontario hiring** — ESA s. 8.4: AI disclosure in job postings
4. **If public sector Ontario** — EDSTA: public-sector AI duties
5. **Plan for C-36** — prepare for the personal information = inferred data shift; right to explanation

The 5 steps cover the current and pending Canadian framework.

## The 4 penalty exposures

| Violation | Penalty |
|---|---|
| Quebec Law 25 breach | CAI orders, fines under Quebec privacy law |
| Ontario ESA breach | employment standards penalties |
| Ontario EDSTA breach | administrative penalties (still being defined) |
| Bill C-36 breach (when in force) | administrative monetary penalties up to greater of $10M or 3% of global revenue; criminal fines up to greater of $25M or 5% of global revenue |

The C-36 penalties, when in force, are EU-AI-Act-tier: 3% of global revenue, 5% on indictment.

## The 5 anti-patterns

1. **Building compliance around AIDA.** AIDA is dead. The framework is privacy law, not AI law.
2. **Assuming Canada = EU AI Act.** Different framework; different obligations; different penalties.
3. **Treating Quebec Law 25 as soft.** It's in force; the CAI enforces.
4. **Missing the Ontario hiring rule.** It applies since January 2026; many companies haven't updated job postings.
5. **Ignoring inferred data.** Bill C-36 makes inferred data personal information; documentation must include inferences.

## The 2-track federal / provincial reality

Canada's AI framework is split between federal (privacy) and provincial (sectoral).

- **Federal layer** — Bill C-36 (pending); AI in scope via personal information
- **Provincial layer** — Quebec Law 25 (active); Ontario ESA + EDSTA (active)
- **The federal layer takes time.** C-36 may pass 2026-2027; in force 2027-2028.
- **The provincial layer is active now.** Law 25 since 2023; ESA since 2026.

A team targeting Canada must plan for both tracks; the provincial layer is the immediate obligation.

## The AI for All strategy (June 4, 2026)

The federal government launched AI for All on June 4, 2026 — a $2B / 5-year strategy.

- **Six pillars:** protection & democratic safeguards, skills, adoption, sovereign infrastructure, Canadian AI companies, international partnerships
- **Not legislation.** A strategy, not a binding law
- **Voluntary commitments** by industry
- **Implication:** signals direction of travel; not enforceable obligations

The strategy is policy, not compliance. Don't plan around it; plan around the binding laws.

## The 3 comparison points vs EU AI Act

| Dimension | EU AI Act | Canada (current) |
|---|---|---|
| Horizontal AI law | yes | no (AIDA dead) |
| Risk classification | 4-tier (unacceptable, high, limited, minimal) | none at federal level |
| Strict-liability for high-risk | yes | no (privacy-based) |
| Penalty for prohibited | 7% global revenue | n/a (no prohibited) |
| Penalty for high-risk non-compliance | 3% global revenue | n/a; under C-36, 3% of global revenue for privacy |

Canada's framework is "AI via privacy" not "AI as its own risk class." The obligations are real but the architecture is different.

## The 4-step Ontario EDSTA pattern

For public-sector AI deployments in Ontario.

1. **Determine if you're a "prescribed public-sector entity"** — defined by EDSTA regulation
2. **Document the AI system** — purpose, decision boundaries, prohibited uses
3. **Conduct an AI impact assessment** — for each new system
4. **Post the assessment** — public registry; transparency obligation

The 4 steps are required for public-sector entities; the private sector is governed by privacy law (C-36 + Quebec Law 25).

## The 5 differences from US state laws

| Dimension | California (SB 53 etc.) | Canada (current) |
|---|---|---|
| Frontier developer scope | $500M revenue + 10^26 ops | none |
| Watermarking | yes (SB 942, Aug 2026) | not at federal level |
| Training data disclosure | AB 2013 (active) | Bill C-36 inferred data |
| Critical incident reporting | 15 days to Cal OES | not at federal level |
| Penalties | $1M per violation | 3% revenue (when C-36 in force) |

The 5 dimensions show Canada's framework is privacy-led; the US framework is AI-led. Different architecture, different obligations.

## Verification

The tell that Canada AI compliance is real:

- Quebec Law 25 obligations implemented (inform, reasons, correction, human review)
- Ontario ESA s. 8.4 hiring disclosure in place
- Inferred data treated as personal information (C-36 preparation)
- Public-sector AI impact assessments (EDSTA) on file
- Documentation includes "general account" of automated decision systems

The tell it isn't:

- "We're complying with AIDA" (AIDA is dead)
- "Canada follows the EU" (different framework)
- No Quebec Law 25 obligations implemented
- No Ontario hiring disclosure
- No C-36 preparation

## Gotchas

- **AIDA is permanently dead.** Don't plan around it; it won't return.
- **Bill C-36 covers AI through privacy.** The trigger is "personal information" (now including inferred); the obligation is explanation + human review.
- **Quebec Law 25 is already enforced.** Don't wait for C-36.
- **Ontario ESA s. 8.4 is in force.** Update job postings now.
- **The federal layer takes time.** C-36 may pass 2026-2027; in force 2027-2028.

## Related

- `issues/eu-ai-act-annex-iii-2026.md` — EU high-risk (different architecture)
- `issues/uk-ai-policy-2026.md` — UK sectoral model
- `issues/california-ai-laws-2026.md` — California AI laws
- `issues/gdpr-article-22-automated-decisions-2026.md` — EU GDPR

## Source URLs (verified 2026-08-10)

- https://airiskaware.com/insights/canada-ai-regulation-2026
- https://peopleofinternet.com/articles/canada-s-bill-c-36-trades-aida-s-broad-ai-rulebook-for-a-nar.html
- https://vorplabs.com/ai-regulatory-updates/canada
- https://www.legal500.com/developments/thought-leadership/canada-tables-bill-c-36-the-protecting-privacy-and-consumer-data-act/
- https://gowlingwlg.com/en-ca/insights-resources/articles/2026/ottawa-tables-long-awaited-federal-privacy-reform-legislation
- https://www.canada.ca/en/innovation-science-economic-development/news/2026/06/ai-for-all.html — AI for All strategy
- https://www.legisquebec.gouv.qc.ca/en/document/cs/P-39.1 — Quebec Law 25
- https://www.ontario.ca/laws/statute/00e41 — Ontario ESA
- https://www.ola.org/en/legislative-business/bills/parliament-43/session-1/bill-194 — Ontario EDSTA
- https://www.parl.ca/legisinfo/en/bill/45-1/c-36 — Bill C-36
