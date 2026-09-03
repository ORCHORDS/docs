# Irreversible Action Warning

## Purpose

Control profile for **OWASP ASI09: Human-Agent Trust Exploitation**.

## Control

Use a distinct warning and confirmation path for actions that cannot be safely undone, rather than presenting them like ordinary agent suggestions.

## Validation

Compare reversible and irreversible test actions and verify the latter cannot reuse a low-friction approval path.

## Failure correction

Stop pending destructive work, restore from recovery mechanisms where possible, and strengthen action classification.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
