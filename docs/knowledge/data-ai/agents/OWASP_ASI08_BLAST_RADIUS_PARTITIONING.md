# Agent Blast Radius Partitioning

## Purpose

Control profile for **OWASP ASI08: Cascading Failures**.

## Control

Partition credentials, queues, data, and execution pools so failure in one agent population or tenant cannot automatically propagate across the whole system.

## Validation

Inject a controlled failure into one partition and verify unrelated partitions retain service and separate authority.

## Failure correction

Isolate the affected partition, rotate shared resources that defeated isolation, and redesign any hidden global dependency.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
