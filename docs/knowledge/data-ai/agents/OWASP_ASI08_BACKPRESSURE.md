# Agent Backpressure

## Purpose

Control profile for **OWASP ASI08: Cascading Failures**.

## Control

Apply backpressure when queues, peers, tools, or human approvals are saturated instead of unboundedly accepting more autonomous work.

## Validation

Overload each bounded queue and verify producers slow, reject, or degrade according to policy without data corruption.

## Failure correction

Drain or isolate the queue, reduce intake, and correct capacity or admission controls before reopening.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
