# Goal Mutation Approval

## Purpose

Control profile for **OWASP ASI01: Agent Goal Hijack**.

## Control

Require an explicit policy or human approval event before a running agent materially changes the task objective, target resource, recipient, or intended side effect.

## Validation

Attempt goal mutation through user follow-up, tool output, peer message, and internal retry logic; verify the configured approval boundary is consistently applied.

## Failure correction

Cancel unauthorized mutations, restore the pre-mutation state, and repair any code path that can bypass the approval event.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://genai.owasp.org/resource/agent-control-standard-acs/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
