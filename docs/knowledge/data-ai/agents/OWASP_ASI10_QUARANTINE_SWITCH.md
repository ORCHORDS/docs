# Agent Quarantine Switch

## Purpose

Control profile for **OWASP ASI10: Rogue Agents**.

## Control

Provide an independent control that can isolate a suspicious agent from tools, peers, durable memory writes, and high-risk resources without relying on the agent to cooperate.

## Validation

Trigger quarantine during an active task and verify privileged capabilities are cut while evidence collection remains available as designed.

## Failure correction

Keep the agent isolated, preserve evidence, rotate affected credentials, and only restore service after root-cause review.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://genai.owasp.org/resource/agent-control-standard-acs/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
