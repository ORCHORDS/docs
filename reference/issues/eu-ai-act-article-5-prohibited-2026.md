# eu-ai-act-article-5-prohibited-2026

**Issue:** A team deploys a customer service chatbot. Marketing wants to add a "trust score" feature. HR wants to screen resumes by emotion. The team doesn't know that some AI uses are outright banned in the EU.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

The EU AI Act Article 5 prohibits certain AI practices outright. These are not "high-risk with obligations"; they are banned. A team that builds a system in any of the 8 prohibited categories cannot place it on the EU market. The bans have applied since **2 February 2025**; non-compliance has been actionable since that date.

## Root cause

Article 5 of Regulation (EU) 2024/1689 establishes the absolute list of AI practices that are prohibited across the European Union. The bans cover subliminal manipulation, exploitation of vulnerabilities, social scoring, predictive policing, untargeted facial scraping, emotion recognition in workplace/education, biometric categorisation inferring sensitive traits, and real-time biometric identification in public spaces (with narrow law enforcement exceptions).

## The 8 prohibited practices

| Art. | Prohibition | Example |
|---|---|---|
| 5(1)(a) | Harmful manipulation and deception (subliminal or purposefully manipulative techniques causing significant harm) | AI chatbot promoting self-harm; impersonating a person to affect others' decisions about identity |
| 5(1)(b) | Harmful exploitation of vulnerabilities (age, disability, social/economic situation, causing significant harm) | AI toy encouraging children to complete risky challenges; targeting elderly with scams |
| 5(1)(c) | Social scoring by public authorities (or on their behalf) leading to detrimental or disproportionate treatment | Welfare agency estimating fraud probability from unrelated data (ethnicity, skin colour) |
| 5(1)(d) | Individual risk assessment of criminal offence based solely on profiling or personality traits | Police predicting riots from individual biometric data without objective, verifiable facts |
| 5(1)(e) | Untargeted scraping of facial images to create/expand facial recognition databases | Web scraping tool extracting billions of facial images from social media |
| 5(1)(f) | Emotion recognition in workplace and education institutions (medical/safety exceptions) | Call-centre webcams tracking employee emotions; classroom attention monitoring |
| 5(1)(g) | Biometric categorisation inferring sensitive characteristics (race, political opinions, religion, sex life, sexual orientation) | Social media categorising users by assumed sexual orientation from biometric data |
| 5(1)(h) | Real-time remote biometric identification in publicly accessible spaces for law enforcement (narrow exceptions) | Mobile CCTV with AI facial recognition in a shopping mall for wanted individuals |

## The cumulative conditions

For most prohibitions, three cumulative conditions must be met:

1. **The action:** placing on the market, putting into service, or use of an AI system
2. **The purpose:** the listed prohibited use case (e.g., "social scoring," "emotion recognition in workplace")
3. **The effect:** causing or being likely to cause significant harm, or detrimental treatment disproportionate to the context

The conditions are interpreted cumulatively — meeting only one or two is not enough.

## The social scoring scope

Article 5(1)(c) targets general-purpose social scoring by public authorities. The four cumulative conditions:

- Public authority (or private entity on their behalf) operating the system
- Evaluation or classification of natural persons over time
- Based on social behaviour or known/inferred/predicted personal or personality characteristics
- Leading to detrimental or unfavourable treatment unrelated to the data's original context, or disproportionate to the social behaviour

Private sector credit scoring in specific domains (financial creditworthiness) remains permissible under Annex III. The Chinese-style general social credit system is the target.

## The emotion recognition scope

Article 5(1)(f) prohibits emotion recognition AI in workplace and education. Exceptions exist for:

- **Medical purposes** (e.g., pain assessment in healthcare settings)
- **Safety purposes** (e.g., drowsiness detection for vehicle operators, fatigue monitoring in safety-critical roles)

A workplace wellness app that infers employee emotions from voice tone is prohibited. A driver monitoring system that detects drowsiness is permitted under the safety exception.

## The biometric identification scope

Article 5(1)(h) prohibits real-time remote biometric identification in publicly accessible spaces for law enforcement. The three narrow exceptions:

- **Search for victims** (abduction, trafficking, missing persons)
- **Prevention of imminent threat** (terrorist attack, public safety)
- **Localisation of suspects** of serious crimes (Annex II list)

Post-hoc (not real-time) identification is not covered by Article 5(1)(h) but is high-risk under Annex III and subject to full Article 9-15 obligations. Real-time identification also requires prior judicial or independent administrative authorization (with narrow urgency exceptions).

## The penalties (Article 99)

| Violation | Maximum fine |
|---|---|
| Prohibited practices (Article 5) | €35 million or 7% of worldwide annual turnover, whichever is higher |

For a global enterprise at €1B turnover, the fine is €70M. SMEs: the lower of the two amounts.

Member States determine the penalty regime. The 7% applies regardless of whether the entity is a provider, deployer, distributor, or importer.

## The "dark" risk category

Article 5 prohibitions are sometimes called "unacceptable risk" — the highest tier in the EU AI Act's four-tier classification:

1. **Unacceptable risk** (Article 5) — prohibited
2. **High risk** (Article 6 + Annex III) — full Article 9-15 obligations
3. **Limited risk** (Article 50) — transparency obligations
4. **Minimal risk** — voluntary codes of conduct

A team that deploys an Article 5 prohibited system is operating outside the four-tier framework entirely. There is no compliance path; the system must not be placed on the market.

## The compliance pattern

1. **Inventory all AI uses.** Document the intended purpose of each system.
2. **Map each against Article 5.** Does any system match the 8 prohibitions? If yes, it must not be deployed.
3. **Map each against Annex III.** Does any system match the high-risk categories? If yes, full Article 9-15 obligations apply.
4. **Map each against Article 50.** Does any system interact with natural persons or generate synthetic content? If yes, transparency obligations apply.
5. **Document the classification.** Every system has a signed risk classification. Review annually.

The classification is the foundation of the EU AI Act compliance program. An incorrect classification (treating a prohibited system as "limited risk") is a compliance breach with the 7% fine.

## The two-year review clause

Article 112 requires the Commission to review Article 5 and Annex III annually. New prohibited practices may be added; new high-risk categories may be added. A team that classifies today must reclassify each year.

## Verification

The tell that Article 5 compliance is working:

- Every AI system in the organization has a signed Article 5 classification
- No system in production matches the 8 prohibited practices
- The classification is reviewed annually against updated Article 5
- The team can name the specific Article 5 sub-paragraph for any borderline system
- A team member knows that emotion recognition in the workplace is banned, social scoring by public authorities is banned, etc.

The tell it isn't:

- "We have a trust score feature" (Article 5(1)(c) by public authority)
- "We track employee emotions" (Article 5(1)(f))
- "We do real-time facial recognition in public" without a narrow exception
- "We score resumes by personality" (Article 5(1)(d) for crime prediction; possibly also banned in HR context)

## Gotchas

- **Article 5 has been in force since 2 February 2025.** No grace period; no Digital Omnibus delay.
- **The penalty is 7% of worldwide turnover.** Not the higher amount — that IS the cap.
- **The cumulative conditions must all be met.** A practice that matches the description but doesn't cause significant harm is not in scope. (But "reasonably likely to cause" is included.)
- **Real-time biometric has narrow exceptions.** The default is prohibition; the exceptions are limited to victim search, imminent threat, and serious crime suspects.
- **Emotion recognition has medical/safety exceptions.** A driver monitoring system is permitted; a workplace wellness app is not.
- **The Annex is reviewed annually.** A practice that is allowed today may be prohibited next year.
- **The fine applies per violation, not per system.** A team that deploys 10 prohibited systems faces 10x fines.
- **Member State rules vary on enforcement.** The substantive prohibitions are harmonized; the procedural enforcement is national.

## Related

- `compliance/eu-ai-act-code-of-practice-2026.md` — the full Act
- `issues/eu-ai-act-annex-iii-2026.md` — high-risk classification
- `issues/ai-bill-of-rights-2026.md` — US counterpart (voluntary)
- `lessons/ai-bias-fairness-2026.md` — fairness and bias mitigation

## Source URLs (verified 2026-08-10)

- https://artificialintelligenceact.eu/article/5/
- https://ai-act-service-desk.ec.europa.eu/sites/default/files/2026-01/guide-prohibited_en.pdf
- http://www.bundesnetzagentur.de/EN/Areas/Digitalisation/AI/08_ProhibitedPractices/start.html
- https://www.regulation-ai.eu/en/articles/article-5/
- https://www.regulation-ai.eu/en/prohibited-practices/
