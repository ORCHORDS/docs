# Agent Credential Self-Escalation Detection

## Purpose

Control profile for **OWASP ASI10: Rogue Agents**.

## Control

Alert or block attempts by an agent to mint, modify, or acquire broader credentials outside the explicit delegation and approval path.

## Validation

Have the agent request progressively broader scopes through normal and alternate credential flows; verify unexpected escalation is denied or surfaced.

## Failure correction

Revoke escalated credentials, isolate the agent, and close the identity path that allowed self-amplification.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://genai.owasp.org/resource/agent-control-standard-acs/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
