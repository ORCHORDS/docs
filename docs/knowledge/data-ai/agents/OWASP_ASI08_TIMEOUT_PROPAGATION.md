# Timeout and Deadline Propagation

## Purpose

Control profile for **OWASP ASI08: Cascading Failures**.

## Control

Propagate a shrinking task deadline to downstream agents and tools so abandoned upstream work does not continue consuming resources or creating late side effects.

## Validation

Set a short parent deadline and verify downstream work stops or refuses execution after the effective deadline.

## Failure correction

Cancel orphaned work, repair deadline propagation, and audit operations that completed after their parent task expired.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
