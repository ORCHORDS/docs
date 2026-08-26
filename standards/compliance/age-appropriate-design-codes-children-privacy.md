# Age-Appropriate Design Codes — Children's Online Privacy

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your online service is likely to be accessed by children (under 18 in most
jurisdictions, under 13 for COPPA) but you have no age-appropriate privacy
settings, no age estimation mechanism, and default settings expose children
to behavioral profiling, targeted advertising, and harmful design patterns.
State and national regulators are actively enforcing children's privacy
laws with escalating penalties.

## Context

Age-Appropriate Design Codes (AADCs) are data privacy and safety frameworks
that require online services likely to be accessed by children to protect
their safety and privacy by design. The UK's Children's Code (ICO, 2021)
was the first; California's AADC (2022) opened a wave of US state
legislation. By August 2026, AADCs have been enacted in California, Maryland,
New Jersey, South Carolina, Nebraska, and Vermont, with more states
advancing bills.

## Legislative landscape (August 2026)

### UK Children's Code (ICO)

- In effect since September 2021. Enforced by the ICO.
- Applies to "information society services" likely to be accessed by
  children under 18 in the UK.
- 15 standards including: best interests of the child, age-appropriate
  application, transparency, data minimization, default settings to high
  privacy, and geolocation off by default.
- Enforcement: ICO has issued enforcement notices and fines under GDPR
  read alongside the Children's Code.

### California AADC (CAADCA)

- Signed into law September 2022. Ninth Circuit ruling March 2026 vacated
  the district court injunction, allowing enforcement of most provisions.
- Applies to online services likely accessed by children under 18.
- Requires Data Protection Impact Assessments (DPIAs) before launching
  new features.
- Prohibits using children's personal information in ways that are
  materially detrimental to their physical health, mental health, or
  well-being.
- Requires default privacy settings to be set to high for child users.

### Other US states (enacted by August 2026)

| State | Year enacted | Effective | Age standard |
|---|---|---|---|
| Maryland | 2024 | 2025 | Under 18 |
| Nebraska | 2025 | 2026 | Under 13 (COPPA) |
| Vermont | 2025 | January 2027 | Under 18 |
| New Jersey | 2026 | TBD | Under 18 |
| South Carolina | 2026 | TBD | Under 13 (COPPA) |

### EPIC 2026 Model Bill

EPIC published a model AADC bill in 2026 designed to withstand First
Amendment challenges, incorporating chatbot protections and updated age
estimation provisions.

## Core requirements across jurisdictions

1. **Default to high privacy** — all privacy and safety settings must
   default to the highest level for users identified or estimated to be
   children.
2. **Age estimation** — implement proportionate age estimation mechanisms.
   The Ninth Circuit upheld California's age estimation requirement in
   March 2026.
3. **Data minimization** — collect only data necessary for the service.
   Prohibit profiling children for advertising purposes.
4. **DPIA requirement** — assess privacy and safety risks to children
   before launching new features or services.
5. **Transparency** — provide age-appropriate privacy notices. Use clear,
   age-appropriate language, not legal boilerplate.
6. **Geolocation** — location tracking must be off by default for children.
7. **Nudge prohibition** — do not use design patterns that encourage
   children to weaken their privacy settings.

## Anti-patterns

- **Relying solely on age gates** — a date-of-birth prompt that children
  can lie through does not constitute age estimation. Regulators expect
  more robust mechanisms.
- **Same experience for all users** — serving identical defaults to adults
  and children fails the "high privacy by default" requirement.
- **Profiling children for ads** — behavioral advertising targeting
  children is prohibited or restricted in every AADC jurisdiction.
- **Dark patterns targeting children** — countdown timers, streak
  mechanics, and social pressure notifications directed at children
  violate nudge prohibitions.

## Gotchas

- **"Likely to be accessed"** — AADCs apply to services that children are
  likely to access, not just services targeted at children. A general-
  audience social media app is in scope if children use it.
- **Age estimation vs. age verification** — these are different. Age
  estimation (probabilistic, privacy-preserving) is generally acceptable;
  age verification (identity documents, biometrics) raises its own privacy
  concerns and may conflict with data minimization requirements.
- **Multi-state patchwork** — with no federal US AADC, companies must
  comply with a patchwork of state laws with different age thresholds,
  effective dates, and enforcement mechanisms.
- **First Amendment challenges** — several AADCs have faced constitutional
  challenges. The March 2026 Ninth Circuit ruling provided clarity for
  California but other states remain untested.

## Verification

- Default privacy settings are set to highest level for child users.
- Age estimation mechanism is deployed and documented.
- DPIAs are completed for all features accessible to children.
- No behavioral advertising is served to users identified as children.
- Geolocation is off by default for child users.
- Privacy notices are available in age-appropriate language.
- Compliance is mapped across all applicable state/national AADCs.

## Related

- `documentation/categories/compliance/coppa-children-online-privacy.md`
- `documentation/categories/compliance/gdpr-data-subject-rights.md`
- `documentation/categories/compliance/eu-ai-act-article-5-prohibited-practices.md`

## Source URLs (verified 2026-08-16)

- ICO Children's Code — https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/childrens-information/childrens-code-guidance-and-resources/
- Kids Code Coalition — https://kidscodecoalition.org/age-appropriate-design-codes/
- Ninth Circuit ruling analysis — https://www.hklaw.com/en/insights/publications/2026/03/ninth-circuit-issues-mixed-ruling-on-california-age-appropriate-design
- EPIC Model AADC — https://epic.org/epic-model-aadc/
