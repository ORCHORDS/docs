# EU AI Act — Risk Classification and Engineering Requirements

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your product uses machine learning for recommendations, content
moderation, fraud detection, or hiring assistance, but you do not know
whether it falls under the EU AI Act's regulatory scope. Engineering
has no documented risk management system, no bias testing process, no
logging retention policy, and no human oversight mechanism. Legal asks
engineering for a compliance assessment, and the team cannot determine
which AI Act category applies or what technical controls are required.

## Context

The EU AI Act (Regulation (EU) 2024/1689) is the world's first
comprehensive AI regulation, establishing a risk-based framework for
AI systems. It entered into force on 1 August 2024, with obligations
phasing in over three years: prohibited practices from 2 February 2025,
GPAI rules from 2 August 2025, and high-risk obligations from 2 August
2026 (Annex III systems) with extensions to December 2027 for some
categories and August 2028 for Annex I safety-component systems. The
Act applies to any AI system placed on the EU market or whose output
is used in the EU, regardless of where the provider is based.

## Risk classification tiers

```
┌──────────────────────────────────────────────┐
│  UNACCEPTABLE RISK — Prohibited              │
│  Social scoring, real-time biometric ID      │
│  in public (with exceptions), manipulation   │
│  → Cannot be deployed in the EU              │
├──────────────────────────────────────────────┤
│  HIGH RISK — Heavy regulation                │
│  Safety components, hiring, credit scoring,  │
│  law enforcement, border control, education  │
│  → Risk management, data governance, logging,│
│    human oversight, conformity assessment     │
├──────────────────────────────────────────────┤
│  LIMITED RISK — Transparency obligations     │
│  Chatbots, deepfakes, emotion detection      │
│  → Must disclose AI use to users             │
├──────────────────────────────────────────────┤
│  MINIMAL RISK — No specific obligations      │
│  Spam filters, game AI, recommendations      │
│  → Voluntary codes of conduct                │
└──────────────────────────────────────────────┘
```

## High-risk AI system categories (Annex III)

| Domain | Examples |
|---|---|
| Biometric identification | Remote facial recognition, emotion detection |
| Critical infrastructure | Energy grid management, water supply control |
| Education | Automated grading, admission decisions |
| Employment | CV screening, interview evaluation, task allocation |
| Essential services | Credit scoring, insurance risk, social benefit eligibility |
| Law enforcement | Predictive policing, evidence evaluation |
| Border control | Travel document verification, risk assessment |
| Justice | Sentencing assistance, legal research for courts |

## Engineering requirements for high-risk systems

### 1. Risk management system (Article 9)

```
Continuous lifecycle process:
  □ Identify and analyze known and foreseeable risks
  □ Estimate and evaluate risks from intended use and misuse
  □ Adopt risk mitigation measures
  □ Test for residual risk acceptability
  □ Document all assessments and decisions
  □ Update throughout the system lifecycle
```

### 2. Data governance (Article 10)

```
Training data requirements:
  □ Document data collection and processing methodology
  □ Bias detection and mitigation procedures
  □ Statistical analysis of training data characteristics
  □ Representativeness assessment for target population
  □ Data quality metrics and validation procedures
  □ Privacy-preserving processing where applicable
```

### 3. Technical documentation (Article 11)

```
Required documentation:
  □ System description and intended purpose
  □ Design specifications and architecture
  □ Training methodology and data sources
  □ Performance metrics and limitations
  □ Risk management documentation
  □ Change log and version history
```

### 4. Automatic logging (Article 12)

```
Logging requirements:
  □ Record all inputs and outputs during operation
  □ Minimum retention: 6 months (or as specified)
  □ Enable traceability of decisions
  □ Support post-deployment monitoring
  □ Tamper-evident log storage
```

### 5. Human oversight (Article 14)

```
Oversight mechanisms:
  □ Human can understand system capabilities and limitations
  □ Human can monitor system operation
  □ Human can interpret system output
  □ Human can override or reverse system decisions
  □ "Stop button" or equivalent intervention mechanism
```

### 6. Accuracy, robustness, cybersecurity (Article 15)

```
Technical requirements:
  □ Declared accuracy levels with test methodology
  □ Resilience to adversarial inputs and data poisoning
  □ Graceful degradation under unexpected conditions
  □ Protection against unauthorized access and manipulation
  □ Monitoring for performance drift post-deployment
```

## GPAI (General-Purpose AI) obligations

```
All GPAI providers:
  □ Technical documentation
  □ Compliance with EU copyright law
  □ Summary of training data content

GPAI with systemic risk (> 10^25 FLOPs training):
  □ Model evaluation and adversarial testing
  □ Serious incident tracking and reporting
  □ Cybersecurity protection measures
  □ Energy consumption documentation
```

## Engineering compliance checklist

| Requirement | Implementation | Evidence |
|---|---|---|
| Risk management | Risk register, impact assessments | Assessment documents, review logs |
| Data governance | Bias testing pipeline, data cards | Test reports, data documentation |
| Logging | Structured logging with retention | Log infrastructure, retention policy |
| Human oversight | Admin dashboard, override UI | Screenshots, user flows |
| Accuracy | Test suites, benchmark results | Performance reports |
| Robustness | Adversarial testing, fuzzing | Red team reports |
| Monitoring | Drift detection, alerting | Dashboard configs, alert history |

## Anti-patterns

- **Risk classification avoidance** — claiming a system is "minimal
  risk" without formal analysis. Regulators can reclassify systems
  based on their actual use, not the provider's self-assessment.
  Document the classification rationale.
- **Checkbox compliance** — implementing technical controls without
  actually using them. A human oversight dashboard that no one
  monitors is not compliant. Controls must be operationally active.
- **Post-hoc documentation** — writing risk assessments after the
  system is in production. The AI Act requires lifecycle risk
  management starting from design. Integrate compliance into the
  development process.
- **Ignoring downstream use** — providing a general-purpose model
  without considering how deployers might use it in high-risk
  contexts. Providers are responsible for foreseeable misuse.

## Gotchas

- **Extraterritorial scope** — the AI Act applies to any AI system
  whose output is used in the EU, regardless of where the provider
  or deployer is located. A US company serving EU customers is in
  scope.
- **Open-source exemptions are limited** — open-source AI models
  are exempt from most requirements UNLESS they are used in high-risk
  applications or are GPAI with systemic risk. The exemption covers
  the model release, not downstream use.
- **Conformity assessment timing** — high-risk systems must undergo
  conformity assessment before being placed on the market. Plan for
  assessment timelines (months, not weeks) in release schedules.
- **AI-generated code tools** — code generation tools like Copilot
  are classified as GPAI. If your product uses AI-generated code in
  safety-critical applications, additional obligations may apply.

## Verification

- AI systems are classified by risk tier with documented rationale.
- High-risk systems have active risk management systems.
- Training data has documented governance and bias testing.
- Automatic logging meets 6-month minimum retention.
- Human oversight mechanisms are operational and tested.
- Technical documentation is maintained and version-controlled.

## Related

- `documentation/categories/compliance/soc2-type-ii-audit-preparation.md`
- `documentation/categories/ai-ml/llm-prompt-injection-defense.md`
- `documentation/categories/compliance/dora-digital-operational-resilience.md`

## Source URLs (verified 2026-08-16)

- EU AI Act Summary 2026: Risk Categories + Compliance — https://gdprlocal.com/eu-ai-act-summary/
- EU AI Act 2026: Penalties, Risk Tiers & Deadlines — https://decodethefuture.org/en/eu-ai-act-explained/
- EU AI Act High-Risk Compliance Technical Guide — https://www.mckennaconsultants.com/eu-ai-act-high-risk-compliance-a-technical-readiness-guide-for-august-2026/
- EU AI Act 2026: What Engineering Teams Must Do — https://powercodegroup.com/blog/eu-ai-act-2026-engineering-teams/
