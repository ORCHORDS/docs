---
title: ISO/IEC 27402:2024 AI Security Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: ISO/IEC 27402:2024 (first edition, 2024-06) — "Information technology — Artificial intelligence — Cybersecurity for AI systems"; https://www.iso.org/standard/83130.html
---

# ISO/IEC 27402:2024 AI Security Governance

## Scope

This card governs how `orchords-docs` evaluates the security posture of AI systems against ISO/IEC 27402:2024. It is the reference input for any KB card that cites an AI system (LLM, classifier, recommender, generative model, agent) and the supporting infrastructure (training, inference, retrieval).

## Why this card exists

ISO/IEC 27402 (Cybersecurity for AI systems) was published in 2024 to fill the gap between general ISO/IEC 27002 controls and AI-specific threats (prompt injection, model inversion, training-data extraction, supply-chain poisoning, agent hijack). Without an explicit card, the KB cites AI systems under generic 27002 controls and misses the AI-specific attack surface.

## Document structure (Clauses 5 — 10)

| Clause | Title | Project interpretation |
|---|---|---|
| 5 | AI system security overview | threat model aligned with 27402 |
| 6 | AI system assets | model weights, training data, prompts, embeddings, retrieval index |
| 7 | AI system threat categories | per 27402 enumeration |
| 8 | AI system security controls | mapped to existing 27002 + new AI-specific controls |
| 9 | AI system security processes | threat modeling, red-teaming, ongoing evaluation |
| 10 | AI system security by phase | development, deployment, operation, retirement |

References: `https://www.iso.org/standard/83130.html`.

## Asset model (Clause 6)

The 27402 asset model explicitly enumerates:

- **Model weights** — the trained parameter set. Sensitive: leaks enable model cloning.
- **Training data** — the corpus used for training. Sensitive: leaks enable privacy attacks.
- **Validation / test data** — held-out evaluation data.
- **Prompts** — input prompts in production inference.
- **Completions** — model outputs in production inference.
- **Embeddings** — vector representations of inputs/outputs.
- **Retrieval index** — vector store content for RAG.
- **Tool descriptions** — function-calling schemas exposed to the model.
- **Agent state** — agent memory, scratchpad, conversation history.

Each asset class has its own threat model.

## Threat categories (Clause 7)

27402 enumerates AI-specific threat categories that the KB cards must enumerate when citing AI:

| Threat | Description |
|---|---|
| Prompt injection | attacker-controlled content overrides system prompt |
| Indirect prompt injection | attacker-controlled content in retrieved data overrides system prompt |
| Model inversion | attacker reconstructs training data from model outputs |
| Training-data extraction | attacker extracts verbatim training data |
| Membership inference | attacker infers whether a record was in training data |
| Adversarial inputs | small perturbations cause misclassification |
| Backdoor trigger | specific input pattern triggers misbehavior |
| Model poisoning | attacker tampers with training data or process |
| Supply chain | attacker substitutes upstream model artifact |
| Model theft | attacker extracts model weights via repeated queries |
| Agent hijack | attacker controls agent through prompt or tool injection |
| Excessive agency | agent performs actions beyond intended scope |

## Controls (Clause 8)

27402 controls map onto ISO/IEC 27002 controls with AI-specific overlays. The KB cards cite both:

| 27402 control | Maps to | Project obligation |
|---|---|---|
| A.5.1 — Inventory of AI assets | ISO/IEC 27002 A.5 | every AI reference card must list assets |
| A.6.1 — Access control for AI assets | ISO/IEC 27002 A.9 | model weights access-controlled; prompts/responses logged |
| A.6.2 — Cryptographic protection | ISO/IEC 27002 A.10 | encryption at rest for model weights and embeddings |
| A.7.1 — Prompt injection defense | new | system prompt isolation; input-output sanitization |
| A.7.2 — Indirect prompt injection defense | new | retrieved data provenance tagging; trust boundary enforcement |
| A.7.3 — Adversarial robustness | new | adversarial evaluation before deployment |
| A.7.4 — Backdoor defense | new | training-data provenance, trigger-pattern scanning |
| A.7.5 — Model poisoning defense | new | training pipeline integrity, hash verification |
| A.7.6 — Supply chain integrity | ISO/IEC 27002 A.15 | model card, model hash, signed model artifacts |
| A.7.7 — Model theft defense | new | rate limiting, output filtering |
| A.7.8 — Agent hijack defense | new | tool-call allowlist, human-in-the-loop for high-risk actions |
| A.7.9 — Excessive agency defense | new | action allowlist, scope enforcement |
| A.7.10 — Privacy preservation | ISO/IEC 27002 A.18 + 27701 | differential privacy, federated learning, output filtering |
| A.7.11 — Explainability | new | SHAP / LIME / attention for every model family |
| A.7.12 — Bias and fairness | new | demographic parity evaluation before deployment |
| A.7.13 — Reproducibility | new | seed-based reproducibility |
| A.7.14 — Auditability | ISO/IEC 27002 A.12 | immutable decision log |

## Processes (Clause 9)

The project enforces the following processes:

- **Threat model** documented in every AI reference card.
- **Red-team evaluation** before each major release (minimum 8 hours of dedicated adversarial work).
- **Continuous evaluation** — automated regression suite covering prompt injection, jailbreak, hallucination, bias.
- **Incident response** — AI-specific runbook under `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`.

## Security by phase (Clause 10)

| Phase | AI-specific requirements |
|---|---|
| Development | reproducible training, signed model artifacts, training data lineage, adversarial evaluation |
| Deployment | model card publication, version pinning, observability wired |
| Operation | drift detection, bias monitoring, retrieval index integrity, agent action logging |
| Retirement | decommission plan, model card archive, output redaction in storage |

## Mandatory pre-flight (before adopting a new AI system in a reference card)

1. AI Impact Assessment (per ISO/IEC 42001) is filed.
2. Threat model covers all 12 categories above.
3. Adversarial evaluation results are documented.
4. Model artifact is signed; provenance is documented.
5. Output filtering is in place.
6. Agent action allowlist is documented (if agent).
7. Continuous evaluation suite is wired.

## Cross-reference

- ISO/IEC 27402 ↔ ISO/IEC 42001 (AIMS): 27402 is the security overlay of 42001.
- ISO/IEC 27402 ↔ ISO/IEC 27002: 27402 adds AI-specific controls to 27002.
- ISO/IEC 27402 ↔ ISO/IEC 23053: 27402 maps threats to the 23053 lifecycle stages.
- ISO/IEC 27402 ↔ NIST AI RMF: crosswalk published by NIST.

## Self-attestation cycle

Every 180 days:

1. Walk every AI reference card and confirm 27402 conformance is documented.
2. Confirm threat models cover all 12 categories.
3. Confirm adversarial evaluation was run in the prior cycle.
4. Update the next-review date.

## Sources

- ISO/IEC 27402:2024: `https://www.iso.org/standard/83130.html`
- ISO/IEC 42001:2023 (AIMS): `https://www.iso.org/standard/81230.html`
- ISO/IEC 23053:2022: `https://www.iso.org/standard/74438.html`
- NIST AI RMF Crosswalk: `https://airc.nist.gov/`
- OWASP LLM Top 10 (2025): `https://owasp.org/www-project-top-10-for-large-language-model-applications/`
- MITRE ATLAS (Adversarial Threat Landscape for AI Systems): `https://atlas.mitre.org/`
