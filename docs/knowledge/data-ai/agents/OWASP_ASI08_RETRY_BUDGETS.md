# Agent Retry Budgets

## Purpose

Control profile for **OWASP ASI08: Cascading Failures**.

## Control

Use bounded retry budgets shared across a logical operation rather than letting each layer retry independently and multiply load.

## Validation

Force a persistent downstream failure and verify total attempts remain within the end-to-end budget.

## Failure correction

Stop the retry storm, reset unhealthy queues, and consolidate retry ownership or budgets across layers.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
