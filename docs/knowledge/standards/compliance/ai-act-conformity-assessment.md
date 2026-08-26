# ai-act-conformity-assessment

**Issue:** EU AI Act (Regulation 2024/1689) conformity assessment requirements for high-risk AI systems
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The EU AI Act creates a risk-tiered framework. High-risk AI systems require mandatory conformity assessment before placing on the EU market. GPAI model providers have separate obligations. Enforcement phases began 2024-2026.

## Pattern / Solution
Risk categories:
- Unacceptable risk: prohibited (social scoring, real-time biometric surveillance in public spaces)
- High risk: mandatory conformity assessment + CE marking (list in Annex III: biometric ID, critical infrastructure, education, employment, essential services, law enforcement)
- Limited risk: transparency obligations (chatbots must disclose AI nature)
- Minimal risk: no obligation

High-risk conformity assessment (Article 43):
For most high-risk systems: self-assessment allowed if following harmonized standards (EN 17763, ISO/IEC 42001)
For biometric identification: mandatory third-party notified body assessment

Required technical documentation (Annex IV):
- General description of AI system, intended purpose, version history
- Design specifications: architecture, training data, performance metrics
- Risk management system documentation (Art. 9)
- Data governance documentation (Art. 10)
- Transparency documentation for users (Art. 13)
- Human oversight measures (Art. 14)
- Accuracy, robustness, cybersecurity measures (Art. 15)

Post-market monitoring (Art. 72):
- Collect and analyze performance data from deployed systems
- Report serious incidents to market surveillance authority within 15 days
- Update conformity documentation when system changes

GPAI models (Art. 51-56):
- All GPAI providers: publish summary of training data, implement copyright policy
- Systemic risk models (>10^25 FLOPs): adversarial testing, incident reporting, cybersecurity measures

## Gotchas
- AI Act applies to providers placing systems on EU market AND deployers in EU — even if provider is outside EU
- "Significant change" to a high-risk system triggers new conformity assessment
- CE marking without notified body involvement is possible for most high-risk systems but requires robust internal documentation
- Timeline: prohibited practices August 2024; GPAI August 2025; high-risk systems August 2026

## Related
- `eu-ai-act.md`
- `eu-ai-act-code-of-practice-2026.md`
- `ethics-ai-governance-framework.md`
