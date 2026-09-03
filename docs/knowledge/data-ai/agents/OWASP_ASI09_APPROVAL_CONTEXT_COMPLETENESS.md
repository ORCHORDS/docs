# Human Approval Context Completeness

## Purpose

Control profile for **OWASP ASI09: Human-Agent Trust Exploitation**.

## Control

Show reviewers the exact action, target, material parameters, source of authority, and meaningful consequences before asking them to approve an agent action.

## Validation

Remove or alter one material field at a time and verify the approval interface refuses to present an ambiguous commit action.

## Failure correction

Invalidate approvals collected with incomplete context, correct the presentation contract, and require re-approval.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
