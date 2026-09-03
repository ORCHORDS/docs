# Agent Behavior Baseline

## Purpose

Control profile for **OWASP ASI10: Rogue Agents**.

## Control

Define observable bounds for an agent's normal tools, destinations, data classes, delegation patterns, and side effects so material deviation is detectable.

## Validation

Replay normal workloads and controlled deviations; verify alerts focus on meaningful behavioral changes rather than model wording alone.

## Failure correction

Quarantine suspicious runs, compare with the last trusted baseline, and update the baseline only through reviewed change.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://genai.owasp.org/resource/agent-control-standard-acs/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
