# Prompt Engineering Discipline Governance

## 1. Scope
This standard defines how teams author, version, evaluate, and
operate prompts used with large language models (LLMs) and other
generative AI systems so that prompt-driven applications remain
predictable, auditable, and aligned with platform risk and quality
expectations.

It applies to all prompts used in production AI services, including
system prompts, tool definitions, retrieval augmented generation
templates, and user-facing prompt builders.

## 2. Normative references
The following documents are referenced and inform the requirements
of this standard:

- OWASP Top 10 for LLM Applications (2025).
- NIST AI Risk Management Framework.
- ISO/IEC 42001:2023 AIMS guidance on generative AI controls.
- Platform AI Risk Tiering Practice Governance.
- Platform AI Model Lifecycle Playbook.

## 3. Terms and definitions
For the purposes of this standard, the following terms apply:

- **System prompt**: a prompt defined by the application to set
  model behaviour, persona, and constraints.
- **Prompt template**: a parameterised prompt that may include
  variable placeholders for user input, tool output, or retrieved
  context.
- **Prompt injection**: an adversarial technique that attempts to
  override the system prompt or intended behaviour through
  untrusted input.
- **Evaluation suite**: a reproducible set of inputs, expected
  behaviours, and scoring criteria used to validate a prompt.

## 4. Prompt authoring
Prompts MUST be authored in version-controlled template files with
explicit variable placeholders and inline documentation of intent.
Free-form prompt strings MUST NOT be assembled from untrusted input
without sanitisation.

## 5. Prompt injection defence
Prompt inputs MUST be treated as untrusted data. Applications MUST
implement input validation, context isolation between system and
user content, and output validation before any downstream action is
taken on the model response.

## 6. Tool and function calling
Tool definitions exposed to the model MUST be limited to the
minimum necessary surface and MUST require explicit user
authorisation for sensitive actions. Tool calls MUST be validated
against an allow-list before execution.

## 7. Retrieval augmented generation
Retrieved context MUST be cited in the model response and MUST be
sourced from approved corpora. The retrieval pipeline MUST log
source identifiers and similarity scores for audit.

## 8. Evaluation
Each production prompt MUST be covered by an evaluation suite that
exercises core behaviours, edge cases, and adversarial inputs.
Evaluation results MUST be reviewed before promotion and after any
material change to the prompt or underlying model.

## 9. Versioning and change control
Prompts MUST be versioned alongside the application code that
consumes them. Material changes to prompts MUST follow the platform
change management procedure and be tracked in the prompt registry.

## 10. Observability
Prompt execution telemetry (input hash, output hash, model
identifier, latency, token usage, refusal flag) MUST be captured
and retained according to the observability data handling
standard.

## 11. Roles and responsibilities
The application owner is accountable for prompt quality and safety.
The AI governance body owns evaluation requirements and risk tier
alignment. The security team owns injection defence guidance.

## 12. Audit and evidence
Prompt versions, evaluation results, and incident records MUST be
retained for at least 24 months in the AI governance archive.

## 13. Review cycle
This standard is reviewed at least annually or when material changes
occur in upstream LLM guidance, platform risk tiering, or
applicable regulation.

---

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
