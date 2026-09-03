# Agent Fan-Out Limits

## Purpose

Control profile for **OWASP ASI08: Cascading Failures**.

## Control

Bound how many subagents, peer requests, or downstream tasks a single task may create so one error cannot expand without limit.

## Validation

Trigger recursive delegation and broad parallel fan-out until the configured ceiling is reached; verify further expansion stops cleanly.

## Failure correction

Cancel excess descendants, reconcile side effects, and lower or partition limits if the tested blast radius is unacceptable.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
