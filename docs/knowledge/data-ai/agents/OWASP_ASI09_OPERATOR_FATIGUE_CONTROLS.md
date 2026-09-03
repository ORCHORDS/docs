# Operator Fatigue Controls

## Purpose

Control profile for **OWASP ASI09: Human-Agent Trust Exploitation**.

## Control

Detect approval volume or repetition likely to cause rubber-stamping and reduce risk through batching, throttling, escalation, or automation of only demonstrably safe cases.

## Validation

Generate sustained approval load and measure whether reviewers are asked to make repetitive high-risk decisions beyond the defined threshold.

## Failure correction

Throttle the workflow, redistribute review, and redesign the approval boundary so human attention is reserved for meaningful decisions.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
