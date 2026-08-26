# ai-system-cards-2026

**Issue:** A team deploys a customer-facing AI agent. The EU AI Act Article 13 requires a transparency document for high-risk systems. The team has no model card, no system card, no datasheet. The auditor asks for documentation; the team has 30 days.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

The EU AI Act's August 2026 deadline makes AI system cards a legal compliance document, not just a transparency best practice. Three documents are involved in a complete AI transparency package: a **model card** (the underlying ML model), a **dataset datasheet** (the training data), and an **AI system card** (the deployed application). Most teams have none of them.

## Root cause

A model card documents the trained ML model — weights, training data, benchmarks, bias evaluation. A dataset datasheet documents the training data — sources, governance, limitations, privacy implications. An AI system card documents the deployed application — the full end-to-end system that users actually interact with, including the model, retrieval layers, safety filters, human oversight mechanisms, and the complete user-facing product context.

Anthropic's Claude 4 system card and OpenAI's GPT-5.5 system card (updated April 24, 2026) both illustrate the system-level scope. The system card is the primary accountability document for the deployed product, satisfying EU AI Act Articles 11, 13, and 50.

## The three documents compared

| Dimension | AI System Card | AI Model Card | Dataset Datasheet |
|---|---|---|---|
| What it documents | The full deployed AI application: model + safety layer + retrieval + usage policy + human oversight + product context | The trained ML model artifact: weights, architecture, training data summary, benchmarks, bias evaluation, known limitations | The training or evaluation dataset: sources, collection methodology, governance, privacy implications, known gaps |
| Primary audience | End users, deployers, regulators, auditors, procurement teams, the general public | AI developers, data scientists, compliance teams, technical evaluators, model deployers | ML researchers, data engineers, compliance and privacy teams, auditors evaluating training data governance |
| EU AI Act | Article 13 (transparency to deployers), Article 50 (transparency to users) | Article 11 (technical documentation), Annex IV | Article 10 (data governance) |

## The EU AI Act Article 13 obligations

For high-risk AI systems, Article 13 requires:

- The system's intended purpose
- The level of accuracy, robustness, and cybersecurity
- Known foreseeable circumstances of relevant risk
- The meaning of the system's output
- How to interpret the output
- Human oversight measures
- Expected lifetime of the system

The Article 13 disclosure must be provided to deployers (the organization operating the system) before the system is put into use. The system card is the primary document satisfying this requirement.

## The EU AI Act Article 50 obligations

Article 50 covers transparency to end users:

- AI systems intended to interact with natural persons must disclose that they are AI
- Synthetic content (images, audio, video, text) must be machine-readable as artificially generated
- Emotion recognition and biometric categorization must inform affected persons
- Users of AI-generated content must disclose the AI involvement

The system card includes the Article 50 compliance section: how the system satisfies the disclosure obligations.

## The system card template (2026)

The 2026 template, designed to satisfy Article 13 and Article 50, contains 8 sections:

**Section 1 — System Overview.** System name, type, provider organization, deployer organization, release date, current version, underlying model(s), access mode, geographic availability.

**Section 2 — Intended Use and Scope.** Primary intended purpose, intended users, intended deployment context, out-of-scope uses.

**Section 3 — Capabilities and Limitations.** Core capabilities, known limitations, performance benchmarks with measurement methodology.

**Section 4 — Safety Measures and Content Policies.** Content safety filters (input and output), usage policy summary, red team testing summary, mitigations applied.

**Section 5 — Data and Privacy.** User data collected, data used for training, data retention period, GDPR compliance.

**Section 6 — Human Oversight and Contestability.** Human oversight mechanisms, AI disclosure to users, contestability and appeal process.

**Section 7 — Performance Monitoring.** Post-deployment monitoring plan, drift detection, incident response process.

**Section 8 — Regulatory Compliance.** EU AI Act classification (prohibited / high-risk Annex III / GPAI / limited / minimal), Article 13 compliance, Article 50 compliance, other applicable frameworks (NIST AI RMF, ISO 42001).

## The required fields for Article 13 compliance

Fields marked with ⚠️ are required for EU AI Act Article 13 or Article 50 compliance for applicable system types:

- System name and version
- Provider organization
- Underlying model(s) and links to model cards
- Intended purpose
- Known limitations
- Performance benchmarks
- Safety measures (input and output)
- Usage policy
- Human oversight mechanisms
- Data governance summary
- EU AI Act classification

Blank fields in a compliance document are treated as missing information by auditors. If a field is not applicable, write "N/A — [one sentence explaining why]" rather than leaving it empty.

## The model card practice

The model card precedes the system card. For each model powering the system, the model card documents:

- Model name, version, training data cutoff
- Architecture summary (e.g., transformer decoder, MoE)
- Training data summary (sources, scale, languages)
- Performance benchmarks (MMLU, HumanEval, GPQA, etc.)
- Bias and fairness evaluation
- Known limitations
- Safety evaluation (red team, refusal rate, etc.)
- Intended use cases
- Out-of-scope uses

Anthropic publishes model cards at `https://www.anthropic.com/system-cards`. Google DeepMind publishes at `https://deepmind.google/models/model-cards/`. OpenAI publishes at `https://openai.com/index/<model>-system-card/`. The model card is the upstream reference; the system card references it.

## The dataset datasheet practice

For each training or fine-tuning dataset, the datasheet documents:

- Dataset name and version
- Composition (size, languages, domains)
- Collection methodology
- Preprocessing steps
- Labeling process (if applicable)
- Privacy and consent
- Known biases and limitations
- Intended use
- Restrictions on use

The datasheet answers "what data was used" and "what are its known limitations." A team cannot answer AI bias questions (EU AI Act Article 10) without the datasheet.

## The maintenance cadence

A system card is not a one-time document. Update triggers:

- After every significant model update (new version, fine-tune)
- After every material change to usage policies or safety mitigations
- After any serious safety incident involving the system
- After any regulatory change that creates new compliance obligations
- At minimum, annually as part of the AIMS review (per ISO 42001 Clause 9)

A team that has not updated its system card in 18 months has a stale compliance document.

## The template sources

Several organizations publish model and system card templates:

- **Anthropic:** publishes model system cards for every Claude release
- **OpenAI:** publishes system cards for every GPT release
- **Google DeepMind:** publishes model cards for every Gemini release
- **Meta:** publishes model cards for Llama releases
- **Hugging Face:** model card template at `https://huggingface.co/docs/hub/model-cards`
- **MITRE ATLAS:** adversarial threat model for AI systems (referenced from safety sections)

For a team building their own template, the EU AI Act Annex IV technical documentation is the authoritative starting point.

## Verification

The tell that system card practice is working:

- Every deployed AI system has a system card, signed by the accountable executive
- Every underlying model has a model card, linked from the system card
- Every training dataset has a datasheet, linked from the model card
- The system card is updated within 30 days of any model upgrade or safety change
- An auditor can pull the system card, model card, and datasheet on demand
- The Article 50 user-facing disclosure (e.g., "I am an AI") is implemented and matches the system card

The tell it isn't:

- A team "intends to write" a system card but has not
- The system card is the vendor's marketing material, not the team's accountability document
- The model card is from the upstream provider and the team's fine-tuning is undocumented
- The datasheet does not exist for fine-tuning data
- The system card has not been updated since launch

## Gotchas

- **A system card is not a marketing page.** It is a legal compliance document. Treat it like a regulatory filing.
- **The vendor's model card is not your system card.** A team deploying a fine-tuned model on top of a foundation model needs both: the foundation model card (vendor's) plus the team's system card for the deployed application.
- **Article 50 is a user-facing obligation.** The system must tell the user it is AI. "I am an AI assistant" or a visible badge. The system card documents how.
- **Update on model upgrades.** A new fine-tune is a material change. The system card must reflect it.
- **Blank fields are missing information.** Auditors treat them as compliance gaps. Use "N/A — [reason]" instead.
- **Three documents, not one.** Model card + dataset datasheet + system card. Each answers a different question for a different audience.
- **The system card is the Article 11/13 deliverable, not the model card.** High-risk AI compliance requires the system-level document.

## Related

- `compliance/eu-ai-act-code-of-practice-2026.md` — full Act structure
- `issues/eu-ai-act-annex-iii-2026.md` — high-risk classification triggers
- `issues/iso-iec-42001-aims-2026.md` — management system standard for AI
- `lessons/ai-bias-fairness-2026.md` — Article 10 obligations

## Source URLs (verified 2026-08-10)

- https://www.anthropic.com/system-cards
- https://deepmind.google/models/model-cards/
- https://openai.com/index/gpt-5-5-system-card/
- https://openai.com/index/gpt-5-5-instant-system-card/
- https://aibuzz.blog/ai-system-cards-explained/
