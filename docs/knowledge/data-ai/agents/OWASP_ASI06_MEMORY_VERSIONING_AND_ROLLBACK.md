# Memory Versioning and Rollback

## Purpose

Control profile for **OWASP ASI06: Memory and Context Poisoning**.

## Control

Version security-relevant memory changes so operators can identify when poisoning entered durable state and restore a known-good snapshot.

## Validation

Introduce a controlled bad memory update, locate its version boundary, and verify rollback removes downstream influence.

## Failure correction

Freeze writes, restore the last trusted version, and replay only verified changes after the incident point.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
