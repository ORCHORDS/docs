# EU AI Act Article 5 — Prohibited AI Practices

**Date:** 2026-08-16
**Author:** the platform team
**Status:** open — enforcement active since February 2, 2025

## Symptom

Your organization deploys or develops AI systems and needs to determine
whether any of them fall under the EU AI Act's outright bans. Unlike high-
risk systems (which require conformity assessment), prohibited practices are
banned entirely — no compliance path, no sandbox, no exception (with narrow
law enforcement carve-outs). Violations carry the highest penalty tier.

## Root cause

Article 5 establishes absolute red lines for AI use in the EU. These
prohibitions took effect on February 2, 2025 — the first provisions of the
AI Act to become enforceable. Penalties: up to €35 million or 7% of global
annual turnover, whichever is higher.

## The eight prohibited practices

### 1. Subliminal manipulation
AI systems that deploy subliminal techniques beyond a person's consciousness
to materially distort behavior in a way that causes or is reasonably likely
to cause significant harm.

### 2. Exploitation of vulnerabilities
AI systems that exploit vulnerabilities due to age, disability, or social or
economic situation to materially distort behavior, causing significant harm.

### 3. Social scoring by public authorities
AI systems used by public authorities (or on their behalf) to evaluate or
classify persons based on social behavior or personal characteristics,
leading to detrimental treatment that is unjustified or disproportionate.

**Key nuance:** the prohibition applies when scoring leads to adverse
treatment in a context unrelated to where the data was generated, or when the
treatment is disproportionate. Private-sector loyalty programs are not
automatically prohibited, but they may be if they produce adverse effects in
unrelated contexts.

### 4. Real-time remote biometric identification (public spaces)
AI systems for real-time remote biometric identification in publicly
accessible spaces for law enforcement. **Narrow exceptions:** targeted search
for specific crime victims or missing children, prevention of imminent
terrorist threat, identification of suspects of serious crimes listed in
Annex II. Each exception requires prior judicial authorization.

### 5. Biometric categorization for sensitive attributes
AI systems that categorize individuals based on biometric data to deduce or
infer race, political opinions, trade union membership, religious or
philosophical beliefs, sex life, or sexual orientation. Exception: labeling
or filtering of lawfully acquired biometric datasets (e.g., sorting photos
by hair color for a search function).

### 6. Predictive policing (individual)
AI systems that make risk assessments of individuals to predict criminal
offending based solely on profiling or personality traits. Exception: AI that
supports human assessment based on objective, verifiable facts directly
linked to criminal activity.

### 7. Facial recognition database scraping
AI systems that create or expand facial recognition databases through
untargeted scraping of facial images from the internet or CCTV footage
(Clearview AI-type systems).

### 8. Emotion recognition in workplace and education
AI systems that infer emotions of individuals in the workplace or in
educational institutions. **Exceptions:** systems for medical or safety
purposes (e.g., fatigue detection for drivers, pilots).

## Compliance checklist

- [ ] **Inventory all AI systems** — catalog every AI system your
  organization develops, deploys, or procures.
- [ ] **Screen against all eight prohibitions** — for each system, determine
  whether it falls within any prohibited category.
- [ ] **Document the analysis** — record why each system is or is not
  prohibited. If it is close to a boundary, document the reasoning.
- [ ] **Review data sources** — ensure no training data was collected via
  prohibited methods (scraping for facial recognition databases).
- [ ] **Review HR/workplace AI** — emotion recognition in employee
  monitoring, hiring assessments, or workplace productivity tools is
  prohibited unless medical/safety exception applies.
- [ ] **Review public-sector deployments** — social scoring and real-time
  biometric identification have the narrowest exceptions.
- [ ] **Legal review of edge cases** — subliminal manipulation and
  vulnerability exploitation prohibitions are broadly worded. Have legal
  counsel review persuasive AI, recommendation algorithms, and
  personalization systems.

## Gotchas

- **"Social scoring" is broader than China's system** — the prohibition
  covers any AI that evaluates people based on social behavior and produces
  adverse treatment in unrelated contexts. Recommendation algorithms that
  affect access to services may qualify.
- **Emotion recognition ban is workplace-specific** — emotion recognition
  in customer service, entertainment, or medical contexts is NOT prohibited
  under Article 5 (though it may be high-risk under Annex III).
- **Private sector is not exempt** — while social scoring is framed around
  public authorities, private companies acting on behalf of or contracted
  by public authorities are covered.
- **"Subliminal" is hard to define** — the boundary between persuasive
  design and subliminal manipulation is legally untested. Expect case law
  to develop.
- **Enforcement is split** — the AI Office enforces against GPAI model
  providers directly. National market surveillance authorities handle other
  cases. Cross-border enforcement coordination is still maturing.

## Related

- `documentation/categories/compliance/eu-ai-act.md`
- `documentation/categories/compliance/eu-ai-act-annex-iii-high-risk-systems-2026.md`
- `documentation/categories/compliance/eu-ai-act-gpai-model-provider-obligations.md`
- `documentation/categories/compliance/ai-act-conformity-assessment.md`
- `documentation/categories/issues/eu-ai-act-article-50-deepfakes-2026.md`

## Source URLs (verified 2026-08-16)

- EU AI Act Article 5 prohibited practices deep dive — https://www.wilmerhale.com/en/insights/blogs/wilmerhale-privacy-and-cybersecurity-law/20240408-prohibited-ai-practices-a-deep-dive-into-article-5-of-the-european-unions-ai-act
- Every Article 5 ban explained — https://aiactbase.eu/prohibited-ai-practices/
- All 8 prohibited AI practices explained — https://euaicompass.com/article-5-prohibited-ai-practices-explained.html
- Red lines: social scoring as prohibited practice — https://fpf.org/blog/red-lines-under-the-eu-ai-act-unpacking-social-scoring-as-a-prohibited-ai-practice/
- EU AI Act FAQ: Article 5 — https://ai-act-service-desk.ec.europa.eu/en/ai-act/faq/what-systems-are-prohibited-under-article-5-ai-act-eg-social-scoring-emotion-recognition
