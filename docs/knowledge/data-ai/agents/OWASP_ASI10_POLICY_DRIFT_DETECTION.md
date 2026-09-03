# Agent Policy Drift Detection

## Purpose

Control profile for **OWASP ASI10: Rogue Agents**.

## Control

Detect when effective runtime policy differs from the reviewed policy version expected for the agent deployment.

## Validation

Change policy content, loading order, or source without updating the approved version and verify the mismatch is visible or blocks execution.

## Failure correction

Stop the affected deployment, restore the approved policy bundle, and fix configuration paths that permit silent substitution.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://genai.owasp.org/resource/agent-control-standard-acs/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
