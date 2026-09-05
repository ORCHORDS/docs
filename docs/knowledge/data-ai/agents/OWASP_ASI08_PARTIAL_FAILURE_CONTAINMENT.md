# Partial Failure Containment

## Purpose

Control profile for **OWASP ASI08: Cascading Failures**.

## Control

Define which subtask failures may be isolated and which require aborting the parent workflow so incomplete success does not silently become accepted state.

## Validation

Fail each dependency class independently and verify the parent reaches the documented partial, retry, compensate, or abort state.

## Failure correction

Stop ambiguous workflows, reconcile committed side effects, and add explicit failure semantics to orchestration.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
