# Agent Idempotency Keys

## Purpose

Control profile for **OWASP ASI08: Cascading Failures**.

## Control

Use stable idempotency identifiers for retryable state-changing operations so transport or agent retries do not duplicate side effects.

## Validation

Repeat the same commit request through timeout and retry paths and verify the service applies the side effect once.

## Failure correction

Reconcile duplicates, add idempotency enforcement at the durable side-effect boundary, and replay the incident scenario.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
