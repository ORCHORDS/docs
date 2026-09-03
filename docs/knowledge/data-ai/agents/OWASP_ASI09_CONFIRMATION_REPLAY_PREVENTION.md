# Human Confirmation Replay Prevention

## Purpose

Control profile for **OWASP ASI09: Human-Agent Trust Exploitation**.

## Control

Bind approval to the exact action version and invalidate it when material parameters, target, policy, or plan change.

## Validation

Approve one action, change a meaningful field, and verify the old confirmation cannot authorize the modified operation.

## Failure correction

Invalidate stale confirmations, bind future approvals to immutable action identifiers, and audit any reused approval.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
