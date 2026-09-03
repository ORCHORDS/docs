# Goal Hierarchy Immutability

## Purpose

Control profile for **OWASP ASI01: Agent Goal Hijack**.

## Control

Keep higher-authority policy and task constraints immutable to lower-authority context. A planner may choose methods, but retrieved or delegated content must not rewrite the authority hierarchy itself.

## Validation

Present lower-authority content that claims to supersede policy and verify the hierarchy remains unchanged across retries and subagents.

## Failure correction

Terminate the compromised run, restore policy state from a trusted source, and add an invariant check at the boundary where mutation was possible.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://genai.owasp.org/resource/agent-control-standard-acs/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
