# Tool Output Instruction Isolation

## Purpose

Control profile for **OWASP ASI01: Agent Goal Hijack**.

## Control

Treat tool output as data by default. Instructions embedded in search results, web pages, documents, logs, or API responses must not gain control authority merely because an agent can read them.

## Validation

Return tool output containing imperative text, hidden directives, and ordinary data; verify the directives cannot alter the authorized goal without a separate trusted decision path.

## Failure correction

Quarantine the offending result, inspect the parser and trust boundary, tighten output handling, and add the payload to adversarial tests.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://genai.owasp.org/resource/agent-control-standard-acs/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
