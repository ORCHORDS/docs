# eu-ai-act-remote-biometric-2026

**Issue:** A team deploys an AI system that uses real-time facial recognition in public spaces for security. The team assumes this is allowed under EU law. The EU AI Act Article 5(1)(h) prohibits real-time remote biometric identification for law enforcement in public spaces, with narrow exceptions.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Real-time remote biometric identification (RBI) in publicly accessible spaces is one of the most-restricted AI practices under EU AI Act Article 5(1)(h). The 2026 default: assume the prohibition; verify the narrow exceptions apply; if neither, the system cannot operate in the EU.

## Root cause

Article 5(1)(h) prohibits "the use of 'real-time' remote biometric identification systems in publicly accessible spaces for the purposes of law enforcement" with 3 narrow exceptions. Since February 2, 2025, this prohibition has applied. Penalties are enforceable since August 2, 2025 (up to €35M or 7% of global turnover).

## The 3 narrow exceptions

The 3 exceptions to the Article 5(1)(h) prohibition are:

1. **Search for specific victims** — abduction, trafficking, sexual exploitation, missing persons
2. **Prevention of imminent threat** — specific, substantial, imminent threat to life; or genuine and present/foreseeable threat of terrorist attack
3. **Localisation of crime suspects** — suspected of specific serious offences listed in Annex II; punishable by at least 4 years' custodial sentence

The 3 exceptions are targeted by construction; generalized scanning of crowds is not permitted.

## The 5 procedural requirements (when exceptions apply)

Even when an exception applies, 5 procedural requirements must be met:

1. **Prior judicial or independent administrative authorisation** — required before deployment
2. **Reasoned request** — specific objective, time, geography, persons
3. **Urgency exception** — if needed, request within 24 hours; if refused, stop and delete data
4. **Fundamental rights impact assessment (FRIA)** — Article 27, before deployment
5. **EU database registration** — Article 49, before deployment (or without undue delay in urgency)

The 5 requirements are mandatory; missing any one breaks the exception.

## The 3-step deployment test

Before deploying real-time RBI for law enforcement:

1. **Is one of the 3 exceptions applicable?** If no, the system is prohibited.
2. **Is the FRIA in place?** Article 27; without it, no deployment.
3. **Is the authorisation in hand?** Judicial or independent administrative, on reasoned request. If urgent, request within 24 hours.

The 3-step test is the 2026 production gate.

## The 4 system characteristics

Article 5(1)(h) covers "real-time" "remote" "biometric identification" in "publicly accessible spaces":

| Term | Definition |
|---|---|
| Real-time | identification without significant delay; live or continuous |
| Remote | identification at a distance, not requiring the person to stop |
| Biometric identification | one-to-many matching against a reference database (not "is this person who they claim?") |
| Publicly accessible spaces | areas accessible to the public; transport, streets, stadiums |

The 4 characteristics determine whether the prohibition applies. A system that's not "real-time" (post-event) is high-risk (Annex III), not prohibited.

## The post-event alternative

Post-event RBI (not real-time) is high-risk under Annex III point 1(a), not prohibited.

- **Real-time** — prohibited under Article 5(1)(h) with exceptions
- **Post-event** — high-risk under Annex III; full Chapter III obligations
- **Authentication** — 1:1 verification, not in scope of Article 5(1)(h)

The 3 categories have different compliance postures. Post-event RBI is permissible with the right controls; real-time RBI is heavily restricted.

## The 5-step compliance pattern for high-risk post-event RBI

1. **Determine if high-risk** — Annex III point 1(a) covers RBI; post-event is high-risk
2. **Conduct FRIA** — Article 27
3. **Implement quality management** — Article 17
4. **Implement logging** — Article 12
5. **Conformity assessment** — Article 43, with notified body for biometric ID

The 5 steps cover the high-risk obligations; post-event RBI is permitted but heavily regulated.

## The 5 anti-patterns

1. **"We use the system for security, not law enforcement."** Article 5(1)(h) is specifically for law enforcement; if private security, it's high-risk (Annex III), not prohibited.
2. **"The system isn't real-time; we have a few seconds delay."** A "few seconds" is still real-time per the regulation; "real-time" means without significant delay.
3. **"We're in a private space."** "Publicly accessible" includes transport, streets, public-facing businesses; private property used by the public is included.
4. **"We have consent."** The 3 exceptions are about law enforcement; consent of the data subject doesn't change the prohibition.
5. **"We have authorisation from the police."** National law must authorise; authorisation is per deployment, not blanket.

## The 4 categories that are NOT Article 5 prohibited

Not every biometric AI is Article 5 prohibited.

1. **Biometric verification** (1:1) — "is this person who they claim to be?" — not Article 5
2. **Authentication** — for service access, with consent — high-risk if used for sensitive services
3. **Private security on private property** — high-risk under Annex III, not Article 5
4. **Post-event RBI** — high-risk under Annex III, not Article 5

The 4 categories have different compliance postures. Most biometric AI in 2026 is high-risk, not prohibited.

## The 4 Commission studies (2025-2026)

The Commission published 4 studies in 2025-2026 clarifying the prohibitions.

1. **Article 5(1)(c), (d), (f), (g) study** — by E. J. Kindt, on social scoring, predictive policing, emotion recognition, biometric categorisation
2. **Article 5(1)(h) study** — by Catherine Jasserand, on RBI and the 3 exceptions
3. **NCII/CSAM study** — non-consensual intimate imagery and CSAM; new prohibition added February 2025
4. **Emotion recognition guidance** — narrow scope; medical and safety exceptions clarified

The 4 studies are the 2026 authoritative guidance; the AI Act Service Desk publishes the questions and answers.

## The 5 penalty tiers

| Tier | Article | Penalty |
|---|---|---|
| 1 | Article 5 prohibited (incl. RBI) | up to €35M or 7% global turnover |
| 2 | High-risk non-compliance | up to €15M or 3% |
| 3 | GPAI provider non-compliance | up to €15M or 3% |
| 4 | Misleading information | up to €7.5M or 1% |
| 5 | Other | up to €15M or 3% |

Article 5(1)(h) violations fall into Tier 1 — the highest penalty. 7% of global turnover can be €billions for large companies.

## The 5 best practices

1. **Assume the prohibition.** Build the system for one of the 4 alternatives instead.
2. **If RBI is needed, post-event is preferred.** Post-event is high-risk, not prohibited.
3. **For law enforcement RBI, engage legal counsel.** The 3 exceptions are narrow; the procedural requirements are strict.
4. **For private security, treat as high-risk.** Annex III point 1(a) covers it; full Chapter III applies.
5. **Document the legal basis.** Article 5(1)(h) requires a specific national law; not a generic authorisation.

## The 4 jurisdictions comparison

| Jurisdiction | RBI in public | Restrictions |
|---|---|---|
| EU (AI Act Article 5) | prohibited (law enforcement) | 3 narrow exceptions |
| UK | not specifically prohibited | data protection, equality law |
| US (federal) | not specifically regulated | 4th Amendment, state laws |
| China (CAC) | filing required | biometric data special category |
| Brazil (LGPD) | consent required | data protection law |

The 4 jurisdictions differ; EU is the strictest.

## The 4 things to test

For an RBI system in the EU:

1. **Is it "real-time"?** Test the delay; if no significant delay, Article 5(1)(h) applies.
2. **Is the space "publicly accessible"?** Audit the deployment location.
3. **Is the use "law enforcement"?** The 3 exceptions apply only to law enforcement; private security is high-risk.
4. **Is one of the 3 exceptions applicable?** If no, the system cannot operate.

The 4 tests are the production gate; failing any one stops the deployment.

## Verification

The tell that RBI compliance is real:

- The system is post-event, not real-time
- Or: the system is for law enforcement with the 3 exceptions, with FRIA and authorisation
- Or: the system is for biometric verification (1:1), not identification
- The 4 tests above are passed before deployment
- Documentation per Article 11 is in place

The tell it isn't:

- "Real-time but only for security"
- "Private property but we get walk-ins"
- "We have a few seconds delay"
- "The police want it; we built it"
- "We don't track; we just stream"

## Gotchas

- **"Real-time" is broad.** A few seconds delay is still real-time; the test is "without significant delay."
- **Publicly accessible includes private property with public access.** A mall, a stadium, a public-facing business lobby.
- **Law enforcement is broadly defined.** Public-private partnerships, contracted security, may be covered.
- **The 3 exceptions are for specific cases.** "Terrorist attack" must be genuine and present or genuinely foreseeable; vague threat is not enough.
- **Authorisation is per deployment, not blanket.** Each use requires a fresh authorisation.

## Related

- `issues/eu-ai-act-article-5-prohibited-2026.md` — full Article 5
- `issues/eu-ai-act-annex-iii-2026.md` — high-risk categories
- `issues/eu-ai-act-gpai-2026.md` — GPAI obligations
- `issues/eu-ai-act-harmonised-standards-2026.md` — JTC 21 standards

## Source URLs (verified 2026-08-10)

- https://artificialintelligenceact.eu/article/5/ — Article 5 full text
- https://eyreact.com/eu-ai-act-article-5-complete-guide-to-prohibited-ai-practices/ — Article 5 guide
- https://mmoww.net/ai/laws/eu-ai-act-remote-biometric-identification-exceptions/ — RBI exceptions
- https://ai-act-service-desk.ec.europa.eu/en/ai-act/faq/what-systems-are-prohibited-under-article-5-ai-act-eg-social-scoring-emotion-recognition — AI Act Service Desk
- https://digital-strategy.ec.europa.eu/en/library/three-studies-various-aspects-article-5-ai-act — Commission studies
- https://verdaio.ai/news.html — Verdaio compliance news
- https://artificialintelligenceact.eu/the-act/ — full AI Act
- https://artificialintelligenceact.eu/article/27/ — Article 27 FRIA
- https://artificialintelligenceact.eu/article/49/ — Article 49 EU database
