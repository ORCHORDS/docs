# Unexpected Agent Persistence Detection

## Purpose

Control profile for **OWASP ASI10: Rogue Agents**.

## Control

Detect new scheduled jobs, durable workers, startup entries, memory writers, credentials, or other persistence created outside the agent's declared lifecycle.

## Validation

Create authorized and unauthorized persistence in a test environment and verify inventory or monitoring distinguishes them.

## Failure correction

Remove unauthorized persistence, rotate related credentials, investigate the creation path, and add detection coverage.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://genai.owasp.org/resource/agent-control-standard-acs/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
