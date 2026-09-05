---
title: "Agent Prompt Injection Response Playbook"
standard: "OWASP Top 10 for LLM Applications (LLM01: Prompt Injection), NIST AI 100-2 Adversarial Machine Learning Taxonomy"
publisher: "OWASP / NIST"
category: "response-playbook"
subcategory: "agent-security"
canonical_url: "https://owasp.org/www-project-top-10-for-large-language-model-applications/"
status: "approved"
classification: "public"
audience: "AI engineering, security operations, agent platform"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# Agent Prompt Injection Response Playbook

## Trigger

A direct or indirect prompt injection is observed against a production AI agent — for example, a user message that coerces the agent to bypass system instructions, a third-party document or web page that injects instructions through retrieval, or a tool response that smuggles further directives back into the agent's context.

## Scope

This playbook applies to conversational, tool-using, and retrieval-augmented agents operating in production. It covers:

- Detection signals from guardrail telemetry, anomaly detectors, and human reports.
- Containment actions to halt ongoing abuse without disrupting legitimate users.
- Eradication of the injection vector from inputs, retrieval content, and tool outputs.
- Recovery and lessons learned, including model and policy updates.

## Inputs

- Alert or ticket with agent identifier, session ID, and observed payload.
- Conversation and tool-call log fragments showing the injection chain.
- Configuration of the guardrail stack (input filters, output filters, retrieval allow-lists).
- Risk register entry linking the agent to its owner, data sensitivity, and customer impact.

## Steps

1. **Confirm the injection.** Inspect the captured context window and tool-call trace. Distinguish prompt injection from policy-violating but legitimate user requests.
2. **Identify the injection surface.** Note whether the injection arrived via user input, retrieved content, or a tool response. Document the offending tool or document identifier.
3. **Contain the active session.** Suspend or rate-limit the agent session; preserve the full context for forensic review. Notify the agent owner and the security on-call rotation.
4. **Quarantine retrieval content.** Remove or flag the offending document, URL, or tool result so future sessions do not re-ingest it. Update the retrieval allow-list.
5. **Update guardrails.** Patch the input filter to recognise the observed pattern and add a regression test in the agent evaluation harness.
6. **Coordinate disclosure.** If a third-party system was the injection source, follow the responsible disclosure workflow; if customer data was exposed, follow the data breach response record template.
7. **Hold review.** Convene the agent security review within five business days to decide on model updates, system prompt hardening, and additional isolation between untrusted and trusted context.

## Escalation

Escalate to incident response when:

- The injection exfiltrated credentials, customer data, or system prompts.
- The agent performed privileged actions (database writes, outbound payments, infrastructure changes) under coercion.
- The injection succeeded against multiple production tenants simultaneously.

Notify legal, privacy, and customer success when regulated data is implicated.

## Evidence

- Full conversation and tool-call log with timestamps.
- Snapshot of the retrieval content or tool response that carried the injection.
- Guardrail alert payload and detector version.
- Containment actions taken, including session suspension timestamp.
- Model and policy updates applied as remediation.

## Completion Criteria

The incident is closed when:

- The injection vector is removed or neutralised.
- A regression test exists for the observed pattern.
- A written post-incident review is filed and corrective actions have owners and dates.
- Customers, regulators, or partners are notified as required.

## Exceptions

- **False positive.** A confirmed pattern match that does not represent a real injection. Record the case to refine detection thresholds.
- **Authorized adversarial test.** Red-team exercise within scope; record separately and link in the evidence register.

## Related Documents

- OWASP Top 10 for LLM Applications (LLM01 Prompt Injection)
- NIST AI 100-2 Adversarial Machine Learning Taxonomy
- NIST SP 800-61 Rev 3 (Incident Handling Guide)
- Agent Security Testing OWASP LLM Guidance
- Agent Configuration Precedence
