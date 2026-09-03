# Tool Use Anomaly Alerting

## Purpose

Control profile for **OWASP ASI02: Tool Misuse and Exploitation**.

## Control

Detect unusual tool sequences, volume, destinations, privilege combinations, or side effects relative to the task and agent role.

## Validation

Replay normal and deliberately abnormal tool chains and verify alerts contain enough context for an operator to assess deviation.

## Failure correction

Quarantine the suspicious run, preserve sequence evidence, tune the rule with confirmed behavior, and review adjacent executions.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://genai.owasp.org/resource/agent-control-standard-acs/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
