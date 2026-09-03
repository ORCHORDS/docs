# Agent Recovery Ordering

## Purpose

Control profile for **OWASP ASI08: Cascading Failures**.

## Control

Define dependency-aware recovery order so agents do not resume before the data, identity, policy, and tool services they require are trustworthy.

## Validation

Recover components in deliberately wrong order and verify readiness gates prevent premature agent execution.

## Failure correction

Pause resumed agents, restore dependencies in the approved sequence, and correct readiness criteria.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
