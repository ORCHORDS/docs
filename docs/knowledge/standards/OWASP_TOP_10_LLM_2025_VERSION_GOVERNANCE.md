# OWASP Top 10 for LLM Applications 2025 Governance

## Purpose

The OWASP Top 10 for LLM Applications (2025 edition) identifies the most critical security risks for applications that integrate large language models (LLMs). The list provides a taxonomy of LLM-specific risks — including prompt injection, sensitive information disclosure, supply chain, data poisoning, output handling, excessive agency, system prompt leakage, vector and embedding weaknesses, misinformation, and unbounded consumption — with descriptions, examples, and mitigation guidance. This article governs the application of the OWASP Top 10 for LLM Applications (2025) so an organization assesses and mitigates LLM-specific risks systematically.

## Scope

The list applies to applications that integrate LLMs, including retrieval-augmented generation (RAG) systems, agents, assistants, and content-generation services. Within this knowledge base, the article covers each of the ten risks, the typical exploitation pattern, and the standard mitigation. It does not replace a broader LLM risk assessment (readers should consult ISO/IEC 42001 for AI management systems and ISO/IEC 23894 for AI risk management).

## Workflow

1. Inventory the LLM applications in the organization: the LLMs used, the integrations, the data flows, and the deployment environments.
2. For each LLM application, assess against the OWASP Top 10 for LLM Applications (2025):
   - LLM01 Prompt Injection: direct and indirect prompt injection; mitigation via input validation, output validation, and segregation of untrusted content.
   - LLM02 Sensitive Information Disclosure: protection of personal data, secrets, and proprietary data; mitigation via data minimization, encryption, and output filtering.
   - LLM03 Supply Chain: vetting of LLMs, embeddings, fine-tuning data, and libraries; mitigation via provenance, integrity verification, and SBOM.
   - LLM04 Data and Model Poisoning: integrity of training and fine-tuning data; mitigation via data provenance, anomaly detection, and human review.
   - LLM05 Improper Output Handling: validation of LLM outputs before downstream use; mitigation via output validation and structured outputs.
   - LLM06 Excessive Agency: scope of actions the LLM can take; mitigation via least privilege, human-in-the-loop, and tool restriction.
   - LLM07 System Prompt Leakage: protection of the system prompt; mitigation via prompt hardening and secret separation.
   - LLM08 Vector and Embedding Weaknesses: integrity of vector stores and embeddings; mitigation via access control, validation, and monitoring.
   - LLM09 Misinformation: factual accuracy of LLM outputs; mitigation via grounding, citations, and human review.
   - LLM10 Unbounded Consumption: resource use by LLMs; mitigation via rate limiting, quotas, and cost monitoring.
3. Apply the mitigations: input validation, output validation, access control, monitoring, rate limiting, and human review.
4. Document the assessment, the mitigations, and the residual risks per application.

## Controls and evidence

LLM controls include the documented assessment, the input/output validation rules, the access control configuration, the monitoring and alerting configuration, the rate limiting configuration, and the human review records. Each application should be traceable to the risks identified and the mitigations applied.

## Validation

Validation should confirm the assessment covers all ten categories, the mitigations are in place, the monitoring and alerting operate, and the applications are re-assessed on changes. Penetration testing, red teaming, and benchmark evaluation confirm the controls.

## Failure correction

Common failure modes: only one or two categories are assessed (correct: assess all ten); mitigations are not implemented (correct: implement the mitigations per the standard); the system prompt contains secrets (correct: move secrets out of the system prompt); rate limiting is not configured (correct: configure rate limits and monitor consumption); outputs are passed to downstream systems without validation (correct: validate outputs before downstream use).

## Limitations

The OWASP Top 10 for LLM Applications (2025) is a prioritized list of risks; it is not a complete LLM risk assessment. The list does not replace a broader AI risk management framework (ISO/IEC 23894) or an AI management system (ISO/IEC 42001). The list is updated periodically; readers should consult the latest version.

## Scope note

This article summarizes project-neutral standards use of the OWASP Top 10 for LLM Applications 2025 edition. It does not assert any specific application's security or claim any certification outcome.

## Canonical sources

- OWASP Top 10 for LLM Applications (2025): https://owasp.org/www-project-top-10-for-large-language-model-applications/
- OWASP LLM AI Security & Governance Checklist: https://owasp.org/llm-security-governance-checklist/