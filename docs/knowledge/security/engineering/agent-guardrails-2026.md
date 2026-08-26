# agent-guardrails-2026

- **Issue**: "Add a guardrail" is not a single thing. Production LLM safety is a six-layer stack, each addressing a distinct threat, each with its own tooling and latency budget. Most teams deploy two layers and call it done.
- **Date**: 2026-08-09
- **Repo**: example-org/example-repo
- **Author**: kb-batch-2
- **Status**: Active; complements `documentation/docs/policies/security/ai-agent-security.md` and `documentation/docs/policies/security/prompt-injection-defense.md`.

## Symptom

- The LLM is wrapped in a content filter. An indirect prompt injection arrives through a RAG chunk. The filter does not catch it because the filter is on outputs, not on retrieved content.
- The guardrail is implemented as a system-prompt instruction. An adversarial input rewrites the system prompt. The guardrail is now a feature of the attack.
- An LLM-judge guardrail hallucinates and approves unsafe content. The recursive check makes the system *less* safe.
- PII makes it to the LLM logs because the redaction was applied to the model output but not to the inbound message.

## Root cause

Safety is a **stack**, not a setting. Each layer addresses a different OWASP 2025 / OWASP Agentic 2026 risk, and the layers compose in a specific order. Skipping one is a known gap.

## The six layers

| # | Layer | Position | Primary OWASP risk | What it catches | Failure action |
|---|---|---|---|---|---|
| **L1** | Input validation | Pre-LLM | LLM01 (direct prompt injection) | PII in input, jailbreak attempts, off-topic, injection classifiers | Block or sanitize before LLM call |
| **L2** | Prompt-template hardening | Pre-LLM | LLM01 + LLM07 (system-prompt leakage) | Role-anchoring, injection resistance, non-disclosure | (Hardening, not a runtime check) |
| **L3** | Retrieval / RAG rail | Pre-LLM (for retrieved data) | LLM01 indirect | Poisoned or adversarial chunks before they enter context | Filter, strip, or quarantine |
| **L4** | Output filtering | Post-LLM | LLM02 (PII) + LLM05 (improper output handling) | Toxic content, PII leakage, hallucinations, malformed JSON | Regenerate, redact, return fallback |
| **L5** | Tool-call / execution gating | Pre-execution | LLM06 (excessive agency) | Out-of-scope tool use, parameter injection, privilege escalation | Validate, scope, block |
| **L6** | Managed moderation API | Async / sync | LLM09 (misinformation) | Probabilistic harm scoring as final check or standalone | Block, escalate, log |

A content filter on outputs does nothing to stop indirect prompt injection. A retrieval rail does nothing for PII in user input. Each layer has a job; deploy them all.

## The 2026 framework landscape

- **NeMo Guardrails 0.9+** — programmable rails in Colang 2.0, multi-modal, < 50 ms per-check latency on GPU. Beta — NVIDIA explicitly states in its README that it is not recommended for production as-is. Plan additional hardening.
- **Guardrails AI 0.5+** — 60+ pre-built validators, RAIL spec for structured output, server mode for production. Best fit for stateless structured-output validation.
- **LLM Guard 0.4+** — zero-dependency scanner library, input + output scanning, PII anonymization built in. Best for fast scanning.
- **OpenAI Moderation API v2** (`omni-moderation-latest`) — free content classification endpoint. 42% better on a 40-language benchmark vs prior model. Rate-limited; not a substitute for runtime PII redaction.
- **AWS Bedrock Guardrails** — managed content filtering, denied topics, PII redaction, hate speech detection. Best when you are already on Bedrock.
- **Microsoft Presidio** — PII detection library, integrated into NeMo and the Guardrails AI Hub.
- **OpenAI Privacy Filter** (2026) — open-weight, runs locally, processes long inputs in one pass, context-aware PII detection in unstructured text.

The 2026 production pattern is **two layers for PII, two layers for content, one layer for retrieval, one layer for tool gating**. Compose by threat model, not by framework.

## The two-layer PII pattern

- **Layer 1: regex (microseconds)** — PCI, SSN, email, phone, credit card, API keys. Catches ~80% of structured PII.
- **Layer 2: model-based** (OpenAI Privacy Filter, Guardrails Hub Presidio, spaCy NER) — names, addresses, MRN, biometric references, half-PII regex misses.
- **Replace with named placeholders** (`[CARD_NUMBER]`, `[EMAIL_REDACTED]`) so the agent can reason about the *fact* that PII existed without ever seeing the value.
- **Apply on both sides** — input so it never enters logs, output so the model cannot echo it back.
- **Log redacted versions only.** If raw is needed for compliance audit, write to a separate, encrypted, access-controlled store.

## Layer 1 — Input validation (specifics)

- Regex for structured PII: SSN `\d{3}-\d{2}-\d{4}`, email RFC 5322, phone E.164, credit card Luhn + range.
- NER for unstructured: Presidio or spaCy.
- Fine-tuned classifier as a second layer for prompt injection (a small BERT trained on injection datasets). The `rebuff` library and LLM Guard ship pre-trained injection classifiers.
- Topic restriction: explicit allowlist / denylist per deployment.

## Layer 2 — Prompt-template hardening (specifics)

- Role anchoring: explicit system-prompt instructions not to reveal the system prompt, tested adversarially.
- Input/data separation: tag the structural position of each input (e.g., `<user_input>...</user_input>`) and instruct the model to treat only the system prompt as authoritative.
- Adversarial testing: a corpus of injection attempts that try to rewrite the system prompt; gate the build on their pass rate.

## Layer 3 — Retrieval rail (specifics)

- Strip zero-width text, off-screen positioned elements, HTML comments from untrusted content before indexing.
- Strip Unicode Tag characters `U+E0000`–`U+E007F`.
- Run a PII / injection scan on every chunk before insert; quarantine on hit.
- Provenance tagging: every chunk carries `source_url`, `ingestion_time`, `trust_level`. Untrusted chunks are tagged untrusted at write time, not at read time.

## Layer 4 — Output filtering (specifics)

- **PII redaction** with Presidio (or Guardrails Hub equivalent) on every output.
- **Content moderation** with a fast classifier (e.g., OpenAI omni-moderation-latest, LlamaGuard).
- **Schema validation** with Pydantic or JSON Schema. **Never trust the LLM to produce valid JSON without verification.** Retry with stricter prompt on failure.
- **Hallucination detection** is two-phase:
  - Retrieval-based verification: is the claim grounded in retrieved context? (RAGAS faithfulness, AlignScore)
  - Self-consistency: ask the same question multiple times at different temperatures; significant divergence = uncertain.
- **Reserve the expensive LLM-judge checks** for responses that need them. Not every token of every request.

## Layer 5 — Tool-call / execution gating (specifics)

- **Pre-execution** — validate function name, parameters, and scope before the call fires. Block out-of-scope tool use, parameter injection, privilege escalation.
- **Post-execution** — inspect the tool result before injecting it back into context. Filter sensitive data in API responses, cap result size to prevent context flooding, detect anomalous result shapes.
- The Rule of Two (see `security/ai-agent-security.md`): an operation can have at most two of (untrusted input, sensitive system, external state change). All three requires HITL.

## Layer 6 — Managed moderation API (specifics)

- A probabilistic harm-scoring endpoint run as the final check.
- Can run async as a monitoring layer before becoming a synchronous gate.
- Best as Layer 6 — it is the safety net, not the primary defense.

## Verification

- **Versioned golden corpus** of labeled inputs (attack + benign) in the same commit as any policy change.
- **Parametrized unit tests** asserting each input is blocked or allowed correctly.
- **Red-team suite** mutating known attacks; gate the build on an attack-success-rate budget.
- **Block rate by category** — injection blocks spiking 5× in an hour means you are under attack.
- **False positive rate** — track user appeals or resubmissions after blocks. High appeal rate = threshold too strict.
- **Latency p50, p95, p99** — guardrail latency should stay under 100 ms at p95.
- **Precision / recall / FPR per guard**, not just pass/fail. Tune thresholds to your product's tolerance.
- **Policy compliance rate** (NeMo's primary metric) — % of interactions fully complying with the guardrail policy.

## Gotchas

- **LLM-judge loops create recursive failure modes.** If the judge hallucinates, it approves unsafe content. Use deterministic checks (regex, schema) wherever possible.
- **NeMo is beta.** Treat NVIDIA's own disclaimer as real. Plan for additional hardening before shipping.
- **Don't let a swallowed exception silently pass.** Test the failure path of every guard (fail-open vs fail-closed).
- **Multilingual is a separate test set.** A guardrail that catches English injection may miss CJK injection.
- **Guardrail configs must be version-controlled files**, not hardcoded in application code.
- **L2 hardening is not a runtime check.** It is a design property of the system prompt. Don't replace L1/L4 with L2.
- **PII redaction on output only is half a feature.** PII on input must also be redacted before logs.
- **The default NeMo moderation threshold is conservative.** Tune it; do not assume the defaults are production-ready.
- **Don't gate on JSON schema and then re-parse the output.** Validate the parsed object, not the raw string.

## Related

- `documentation/docs/policies/security/ai-agent-security.md` — the broader agentic threat model
- `documentation/docs/policies/security/prompt-injection-defense.md` — input-side defenses
- `documentation/docs/policies/security/owasp-top-10-2025.md` — the non-agentic OWASP catalog
- `documentation/docs/policies/security/owasp-api-top-10-2023.md` — the API layer
- `documentation/docs/policies/lessons/human-in-the-loop.md` — the escalation layer for blocked actions
- `documentation/docs/policies/patterns/multi-agent-orchestration.md` — where the deterministic validation gate lives

## Source URLs (verified 2026-08-09)

- "LLM Guardrails: Production Safety Layers Reference 2026" (digitalapplied) — https://www.digitalapplied.com/blog/llm-guardrails-production-safety-layers-reference-2026
- "AI Guardrails — Production LLM Safety Guide (2026)" — https://myengineeringpath.dev/genai-engineer/ai-guardrails/
- "LLM Guardrails Testing in 2026" (qaskills) — https://qaskills.sh/blog/llm-guardrails-testing-guide-2026
- NVIDIA NeMo Guardrails evaluation docs — https://docs.nvidia.com/nemo/guardrails/evaluation/evaluate-guardrails
- NVIDIA blog: "Measuring the Effectiveness and Performance of AI Guardrails" — https://developer.nvidia.com/blog/measuring-the-effectiveness-and-performance-of-ai-guardrails-in-generative-ai-applications/
- "AI guardrails: the complete guide for LLMs in January 2026" (openlayer) — https://www.openlayer.com/blog/ai-guardrails-llm-guide
- "Real-Time PII Redaction in Chat Agents" (callsphere) — https://callsphere.ai/blog/vw3b-pii-redaction-chat-agent-guardrails-2026
- "AI guardrails: content moderation and PII redaction" (veloriatech) — https://veloriatech.com/blogs/ai-guardrails-content-moderation-and-pii-redaction
- Guardrails AI Hub — https://hub.guardrailsai.com/
- Microsoft Presidio — https://github.com/microsoft/presidio
