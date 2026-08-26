# llm-prompt-injection-trust-boundaries

**Issue:** An LLM application treats retrieved text, uploaded files, web pages, or tool results as trusted instructions
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Symptom

A summarizer, RAG assistant, or autonomous agent follows instructions embedded in a document or webpage, leaks context, selects a dangerous tool call, or persuades a user to take an unsafe action.

## Root cause

Natural-language instructions and data share the model context, so prompt formatting alone cannot reliably turn hostile content into inert data. OWASP identifies direct and indirect prompt injection as a leading LLM application risk. An indirect injection can arrive through content that the user never typed, such as a retrieved page or uploaded document.

**Source:** [OWASP — LLM01:2025 Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) and the [OWASP prevention cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html).

## Fix

Design the application so model output is a proposal, not authority:

- label all external and user-controlled material as untrusted data at ingestion and preserve its provenance;
- do not grant tools ambient credentials; use per-tool, least-privilege scopes and require server-side authorization for every action;
- require explicit user confirmation for consequential actions, including sending messages, spending money, changing access, deleting data, or exporting data;
- constrain tool calls with typed schemas, allowlists, parameter validation, rate limits, and maximum side-effect budgets;
- separate retrieval from instruction policy, redact secrets before model context assembly, and never place secrets in system prompts;
- test direct and indirect injections in CI and log attempted tool calls, denials, confirmations, and retrieval sources without logging sensitive prompt contents.

## Verification

- **Direct injection:** requests to override policy cannot grant additional tool permissions.
- **Indirect injection:** hostile instructions in a retrieved document are displayed as content and cannot trigger a tool action.
- **Authorization:** a valid-looking model tool call is rejected when the caller lacks the server-side permission.
- **Regression:** the red-team corpus runs in CI with expected denies and no secret disclosure.

## Gotchas

- “Ignore previous instructions” filters are not a security control.
- Human approval is valuable only when the user sees the actual consequence and target, not a vague confirmation prompt.
- Treat tool output as untrusted too: a compromised integration can return attacker-controlled instructions.

## Related

- the OWASP LLM top 10 guidance in this file
- `security/secrets-rotation-runbook-2026.md` or the rotation section in this file
- `cloudflare/cloudflare-sandbox-sdk-untrusted-code.md`
