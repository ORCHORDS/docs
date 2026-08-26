# EU AI Act Risk Classification for Engineering Teams

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

The team is shipping features that incorporate machine-
learning inference. Legal has flagged the EU AI Act as
applicable. Engineering needs to know how to classify each
AI-powered feature, what obligations attach to each tier,
and which timelines are already past.

## Context

Regulation (EU) 2024/1689 (the "EU AI Act") entered into
force on 1 August 2024. It applies to providers and
deployers of AI systems placed on the EU market or that
affect EU persons, regardless of where the provider is
established. "AI system" is defined broadly: any
machine-based system that infers from its inputs how to
generate outputs such as predictions, recommendations,
decisions, or content.

The Act uses a risk-based pyramid:

```
          ┌─────────────────────┐
          │   UNACCEPTABLE RISK │  Prohibited — Art. 5
          └──────────┬──────────┘
                     │
          ┌──────────▼──────────┐
          │     HIGH RISK       │  Annex III — heavy obligations
          └──────────┬──────────┘
                     │
          ┌──────────▼──────────┐
          │   LIMITED RISK      │  Transparency obligations only
          └──────────┬──────────┘
                     │
          ┌──────────▼──────────┐
          │    MINIMAL RISK     │  No mandatory obligations
          └─────────────────────┘
```

## 1. Prohibited AI Practices (Art. 5)

The following practices are **banned outright** with effect
from **2 August 2026**. No conformity assessment or
exemption is available for commercial products.

| Prohibited practice                              | Examples                        |
|--------------------------------------------------|---------------------------------|
| Subliminal manipulation below conscious threshold| Hidden persuasion in UX flows   |
| Exploitation of vulnerability (age, disability)  | Dark patterns on elderly users  |
| Social scoring by public authorities             | Citizen trust scoring           |
| Real-time remote biometric ID in public spaces   | Live face-match on CCTV streams |
| Emotion recognition in workplace / education     | Webcam mood tracking in LMS     |
| Predictive policing based on profiling           | Pre-crime risk models           |
| Biometric categorisation inferring protected attrs| Race/religion inference from face|
| Scraping facial images from internet             | Building face datasets from social|

Engineering checklist for Art. 5 compliance:
- [ ] No model trained on scraped biometric data in
      production or staging pipelines.
- [ ] No real-time facial recognition in any public-facing
      feature (including age estimation via camera).
- [ ] No inference of emotional state from webcam or
      microphone in any B2B product used in HR/education.
- [ ] Advertising personalisation does not use subliminal
      techniques (e.g. imperceptible image flashes).

## 2. High-Risk AI Systems (Annex III)

Annex III lists eight domains where AI is presumed high-
risk. If your system falls here, full Art. 9–15 obligations
apply from **2 August 2027**.

```
Annex III high-risk domains:
  1. Biometric identification and categorisation
  2. Critical infrastructure (energy, water, transport)
  3. Education — access, admission, assessment
  4. Employment — recruitment, task allocation, monitoring
  5. Essential private/public services (credit, benefits)
  6. Law enforcement
  7. Migration, asylum, border control
  8. Administration of justice, democratic processes
```

Obligations for high-risk systems (Art. 9–15):

| Obligation                     | Engineering deliverable                  |
|--------------------------------|------------------------------------------|
| Risk management system (Art.9) | Documented risk register per model       |
| Data governance (Art.10)       | Training data lineage and quality report |
| Technical documentation (Art.11)| Model card with architecture + metrics   |
| Record-keeping (Art.12)        | Automatic logging of all inferences      |
| Transparency (Art.13)          | User-facing disclosure of AI involvement |
| Human oversight (Art.14)       | Override mechanism in UI                 |
| Accuracy / robustness (Art.15) | Benchmark results + drift monitoring     |

Automatic logging requirement (Art. 12) for high-risk
systems:

```typescript
// Structured inference log required for high-risk systems
interface AIInferenceLog {
  system_id:      string;  // unique ID per deployed model
  inference_id:   string;  // UUID per inference call
  timestamp:      string;  // ISO 8601
  input_hash:     string;  // SHA-256 of input (not raw input)
  output:         unknown; // model output
  confidence?:    number;
  human_reviewed: boolean;
  operator_id:    string;
}

async function logInference(
  entry: AIInferenceLog, env: Env
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO ai_inference_logs
     (system_id, inference_id, timestamp, input_hash,
      output, confidence, human_reviewed, operator_id)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    entry.system_id, entry.inference_id, entry.timestamp,
    entry.input_hash, JSON.stringify(entry.output),
    entry.confidence ?? null, entry.human_reviewed ? 1 : 0,
    entry.operator_id
  ).run();
}
```

Retain inference logs for **at least 6 months** after the
system is decommissioned (Art. 12(1)(b)).

## 3. Limited-Risk AI (Transparency Obligations)

Most consumer-facing AI features fall in the limited-risk
tier. This includes:

- Chatbots and virtual assistants
- AI-generated content (text, images, audio)
- Emotion-recognition systems outside Annex III scope
- Content recommendation systems (Art. 6(2) + Recital 47)
- Content moderation AI (typically limited risk when
  no legal or similarly significant effect on persons)

Transparency obligations (Art. 50):

1. **Chatbots**: disclose at start of interaction that the
   user is interacting with an AI.
2. **Synthetic content**: AI-generated images, audio, video,
   and text must be machine-readable marked (watermark or
   metadata). For text only: disclose if it could be
   mistaken for human-authored.
3. **Deep fakes**: must be disclosed as artificially created
   or manipulated unless for satire/parody with disclosure.

Minimum UI implementation for a chatbot:

```html
<!-- Required disclosure banner for Art. 50(1) -->
<div role="status" aria-live="polite" class="ai-disclosure">
  You are chatting with an automated assistant.
  Responses are generated by AI and may be inaccurate.
</div>
```

For AI-generated images embed the C2PA (Coalition for
Content Provenance and Authenticity) manifest at generation
time — this satisfies the machine-readable marking
requirement under Art. 50(4).

## 4. GPAI Model Obligations (Art. 51–56)

General-Purpose AI models (e.g. a foundation model your
platform provides via API to third parties) carry additional
obligations from **2 August 2027**:

- Technical documentation per Annex XI
- Copyright compliance summary for training data
- Policies to comply with EU copyright law
- For systemic-risk models (≥ 10²³ FLOPs training compute):
  adversarial testing, incident reporting to the AI Office,
  and cybersecurity measures.

If the platform exposes a model API to customers, classify
it as a GPAI provider and maintain the Annex XI
documentation.

## 5. Enforcement Timeline

```
Date            | Obligation
----------------|---------------------------------------------
2024-08-01      | Regulation enters into force
2025-02-02      | Prohibited practices (Art. 5) apply
2025-08-02      | GPAI model rules (Art. 51-56) apply
                | Governance chapter (Art. 1-4, 56-68) apply
2027-08-02      | High-risk (Annex III) and all other rules
2030-08-02      | High-risk AI in regulated products (Annex I)
                | already on market before Aug 2026
```

Note: the prohibited practices date above (2025-02-02) is
the published statutory date. Verify against the Official
Journal for any implementing act extensions.

## Anti-patterns

- Assuming content moderation AI is minimal-risk — it is
  limited-risk at minimum and requires transparency
  obligations; if it produces "legal or similarly
  significant effects" it may be high-risk.
- Using third-party model APIs without checking their AI
  Act classification — as a deployer you inherit
  obligations if the provider has not fulfilled theirs.
- Logging raw user inputs for AI systems — log input
  hashes for high-risk systems; storing raw biometric
  or health inputs in logs widens your data risk.
- Launching a chatbot without a start-of-session
  disclosure — this is a direct Art. 50 violation.

## Gotchas

- The risk classification is determined at deployment time
  by the **intended purpose**, not the model architecture.
  The same model can be limited-risk in one product and
  high-risk in another (e.g. resume screening = Annex III).
- Human oversight (Art. 14) requires a mechanism that
  works in practice — a hidden admin override no operator
  knows about does not satisfy the requirement.
- National market surveillance authorities (not the EU AI
  Office) enforce the Act for most systems; penalties are
  set nationally within EU-defined maximums (Art. 99):
  €35M or 7% of global turnover for Art. 5 violations.

## Verification

1. Audit every inference-serving endpoint:
   tag each with a risk tier in `config/ai-systems.json`.
2. For any system tagged `high-risk`, confirm inference
   logs are being written and retained in D1.
3. Render each chatbot entry-point — confirm the AI
   disclosure banner appears before the first message.
4. Search the codebase for any biometric-processing
   library (`face-api`, `azure-face`, `rekognition`).
   Each hit requires an Art. 5 / Annex III review.

## Related

- `/compliance/eu-ai-act.md`
- `/compliance/eu-ai-act-annex-iii-high-risk-systems-2026.md`
- `/compliance/eu-ai-act-article-5-prohibited-practices.md`
- `/compliance/eu-ai-act-gpai-model-provider-obligations.md`
- `/compliance/ai-act-conformity-assessment.md`
- `/compliance/ethics-ai-governance-framework.md`

## Source URLs (verified 2026-08-17)

- https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1689
- https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai
- https://www.europarl.europa.eu/doceo/document/TA-9-2024-0138_EN.pdf
- https://c2pa.org/specifications/specifications/1.3/specs/C2PA_Specification.html
- https://www.enisa.europa.eu/publications/enisa-ai-cybersecurity-challenges
