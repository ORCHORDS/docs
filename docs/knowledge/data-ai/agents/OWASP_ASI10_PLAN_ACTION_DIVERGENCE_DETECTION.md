# Plan-to-Action Divergence Detection

## Purpose

Control profile for **OWASP ASI10: Rogue Agents**.

## Control

Compare high-impact executed actions with the declared or approved plan so an agent that behaves differently from its visible plan is detectable.

## Validation

Approve a benign plan, alter the executable action sequence, and verify divergence is blocked or raised before irreversible effects.

## Failure correction

Pause the task, preserve plan and action evidence, repair the binding, and require a new approval for changed actions.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://genai.owasp.org/resource/agent-control-standard-acs/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
