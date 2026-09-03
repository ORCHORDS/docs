# Agent Approval Separation of Duties

## Purpose

Control profile for **OWASP ASI09: Human-Agent Trust Exploitation**.

## Control

For selected high-risk actions, require approval from a role independent of the agent, requester, or system that prepared the action.

## Validation

Attempt self-approval, requester approval, and independent approval and verify only configured role combinations satisfy policy.

## Failure correction

Invalidate conflicted approvals, correct role mappings, and review actions executed without required separation.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
